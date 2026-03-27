<script lang="ts">
	import { onMount, tick } from 'svelte';
	import type { Modes, TranscriptEntry, RoundData, DebateStatus } from '$lib/types';

	import Sidebar from '$lib/components/Sidebar.svelte';
	import DebateControls from '$lib/components/DebateControls.svelte';
	import StatusBar from '$lib/components/StatusBar.svelte';
	import RoundBlock from '$lib/components/RoundBlock.svelte';
	import VerdictBlock from '$lib/components/VerdictBlock.svelte';
	import FollowupInput from '$lib/components/FollowupInput.svelte';
	import TranscriptViewer from '$lib/components/TranscriptViewer.svelte';
	import ThemeToggle from '$lib/components/ThemeToggle.svelte';

	// ── State ──────────────────────────────────────────────────
	let modes: Modes = $state({});
	let transcripts: TranscriptEntry[] = $state([]);
	let selectedTranscript: { filename: string; content: string } | null = $state(null);

	let question = $state('');
	let selectedMode = $state('debate');
	let selectedRounds = $state(3);
	let unlimited = $state(false);

	let status: DebateStatus = $state('idle');
	let sessionId = $state('');
	let currentAgentColors: Record<string, string> = $state({});
	let rounds: RoundData[] = $state([]);
	let currentSpinner = $state('');
	let verdict = $state('');
	let verdictTitle = $state('');
	let errorMessage = $state('');
	let infoMessages: string[] = $state([]);

	let followupText = $state('');
	let followupResponses: { question: string; responses: Record<string, string> }[] = $state([]);

	let debateLogEl: HTMLElement | undefined = $state();
	let sidebarOpen = $state(false);
	let activeEventSource: EventSource | null = $state(null);

	// ── Lifecycle ──────────────────────────────────────────────
	onMount(async () => {
		const [modesRes, transRes] = await Promise.all([
			fetch('/api/modes'),
			fetch('/api/transcripts'),
		]);
		modes = await modesRes.json();
		transcripts = await transRes.json();
	});

	// ── Helpers ────────────────────────────────────────────────
	async function scrollToBottom() {
		await tick();
		if (debateLogEl) debateLogEl.scrollTop = debateLogEl.scrollHeight;
	}

	async function refreshTranscripts() {
		transcripts = await (await fetch('/api/transcripts')).json();
	}

	function reset() {
		rounds = [];
		verdict = '';
		verdictTitle = '';
		errorMessage = '';
		infoMessages = [];
		currentSpinner = '';
		followupResponses = [];
		sessionId = '';
		selectedTranscript = null;
	}

	function newDebate() {
		reset();
		question = '';
		status = 'idle';
	}

	// ── Stop ───────────────────────────────────────────────────
	function stopDebate() {
		if (activeEventSource) { activeEventSource.close(); activeEventSource = null; }
		currentSpinner = '';
		status = rounds.length > 0 ? 'done' : 'idle';
		infoMessages = [...infoMessages, 'Session stopped by user.'];
		refreshTranscripts();
	}

	// ── Launch ─────────────────────────────────────────────────
	function launchDebate() {
		if (!question.trim() || isRunning) return;
		reset();
		status = 'running';

		const params = new URLSearchParams({
			question: question.trim(),
			mode: selectedMode,
			rounds: String(selectedRounds),
			unlimited: String(unlimited),
		});

		const es = new EventSource(`/api/debate/stream?${params}`);
		activeEventSource = es;

		es.addEventListener('session', (e) => {
			const d = JSON.parse(e.data);
			sessionId = d.session_id;
			currentAgentColors = d.agents;
		});
		es.addEventListener('round_start', (e) => {
			const d = JSON.parse(e.data);
			currentSpinner = d.spinner;
			rounds.push({ round: d.round, title: d.title, responses: {} });
			rounds = rounds;
			scrollToBottom();
		});
		es.addEventListener('round_responses', (e) => {
			const d = JSON.parse(e.data);
			const idx = rounds.findIndex((r) => r.round === d.round);
			if (idx >= 0) { rounds[idx].responses = d.responses; rounds = rounds; }
			currentSpinner = '';
			scrollToBottom();
		});
		es.addEventListener('judging', () => { status = 'judging'; currentSpinner = 'Delivering verdict...'; scrollToBottom(); });
		es.addEventListener('verdict', (e) => {
			const d = JSON.parse(e.data);
			verdict = d.verdict; verdictTitle = d.title; currentSpinner = '';
			scrollToBottom();
		});
		es.addEventListener('info', (e) => { infoMessages = [...infoMessages, JSON.parse(e.data).message]; scrollToBottom(); });
		es.addEventListener('error', (e) => {
			try { errorMessage = JSON.parse(e.data).message; } catch { errorMessage = 'Connection lost'; }
			status = 'error'; currentSpinner = ''; es.close(); activeEventSource = null;
		});
		es.addEventListener('done', () => { status = 'done'; es.close(); activeEventSource = null; refreshTranscripts(); });
		es.onerror = () => {
			if ((status === 'running' || status === 'judging') && verdict) status = 'done';
			es.close(); activeEventSource = null;
		};
	}

	// ── Follow-up ──────────────────────────────────────────────
	function sendFollowup() {
		if (!followupText.trim() || !sessionId || status !== 'done') return;
		const fq = followupText.trim();
		followupText = '';
		status = 'running';
		currentSpinner = 'Agents responding...';

		const es = new EventSource(`/api/followup/stream?${new URLSearchParams({ session_id: sessionId, followup: fq })}`);
		activeEventSource = es;

		es.addEventListener('followup_responses', (e) => {
			followupResponses = [...followupResponses, { question: fq, responses: JSON.parse(e.data).responses }];
			currentSpinner = '';
			scrollToBottom();
		});
		es.addEventListener('error', (e) => {
			try { errorMessage = JSON.parse(e.data).message; } catch { errorMessage = 'Connection lost'; }
			currentSpinner = ''; status = 'done'; es.close(); activeEventSource = null;
		});
		es.addEventListener('done', () => { status = 'done'; es.close(); activeEventSource = null; refreshTranscripts(); });
		es.onerror = () => { es.close(); activeEventSource = null; status = 'done'; };
	}

	// ── Transcript ─────────────────────────────────────────────
	async function viewTranscript(filename: string) {
		const data = await (await fetch(`/api/transcripts/${filename}`)).json();
		if (!data.error) { selectedTranscript = data; sidebarOpen = false; }
	}

	// ── Key handler ────────────────────────────────────────────
	function onKeydown(e: KeyboardEvent) {
		if (e.key !== 'Enter' || e.shiftKey) return;
		const t = e.target as HTMLElement;
		if (t?.classList?.contains('followup-input') && followupText.trim()) sendFollowup();
		else if (t?.classList?.contains('question-input') && !isRunning) launchDebate();
	}

	// ── Derived ────────────────────────────────────────────────
	let hasDebate = $derived(rounds.length > 0 || !!verdict);
	let isRunning = $derived(status === 'running' || status === 'judging');
	let completedRoundCount = $derived(rounds.filter(r => Object.keys(r.responses).length > 0).length);
</script>

<svelte:window on:keydown={onKeydown} />

<div class="app">
	<Sidebar
		{transcripts}
		open={sidebarOpen}
		onToggle={() => (sidebarOpen = !sidebarOpen)}
		onRefresh={refreshTranscripts}
		onSelect={viewTranscript}
	/>

	<main class="main">
		<div class="top-bar">
			<ThemeToggle />
		</div>

		{#if selectedTranscript}
			<TranscriptViewer transcript={selectedTranscript} onClose={() => (selectedTranscript = null)} />
		{:else}
			<DebateControls
				bind:question
				bind:selectedMode
				bind:selectedRounds
				bind:unlimited
				{modes}
				{isRunning}
				{hasDebate}
				onLaunch={launchDebate}
				onStop={stopDebate}
				onNewDebate={newDebate}
			/>

			<StatusBar
				spinner={currentSpinner}
				completedRounds={completedRoundCount}
				visible={isRunning && !!currentSpinner}
			/>

			{#if hasDebate || isRunning}
				<div class="debate-log" bind:this={debateLogEl}>
					{#each rounds as round}
						<RoundBlock {round} agentColors={currentAgentColors} />
					{/each}

					{#each infoMessages as msg}
						<p class="info-message">{msg}</p>
					{/each}

					{#if verdict}
						<VerdictBlock {verdict} title="Verdict" />
					{/if}

					{#each followupResponses as fu}
						<RoundBlock followup={fu} agentColors={currentAgentColors} isFollowup />
					{/each}

					{#if errorMessage}
						<p class="error-message">{errorMessage}</p>
					{/if}
				</div>

				{#if status === 'done' && sessionId}
					<FollowupInput bind:value={followupText} onSend={sendFollowup} disabled={!followupText.trim()} />
				{/if}
			{/if}
		{/if}
	</main>
</div>

<style>
	.app {
		display: flex;
		height: 100vh;
		overflow: hidden;
	}
	.main {
		flex: 1;
		display: flex;
		flex-direction: column;
		overflow: hidden;
		padding: 24px 40px;
		gap: 16px;
		max-width: 960px;
		margin: 0 auto;
		width: 100%;
		position: relative;
	}
	.top-bar {
		display: flex;
		justify-content: flex-end;
		flex-shrink: 0;
	}
	.debate-log {
		flex: 1;
		overflow-y: auto;
		display: flex;
		flex-direction: column;
		gap: 24px;
		padding: 4px 0 16px;
	}
	.info-message {
		font-size: 12px;
		color: var(--text-muted);
		padding: 2px 0;
		font-family: var(--font-mono);
	}
	.error-message {
		font-size: 13px;
		color: var(--red);
		padding: 10px 14px;
		background: color-mix(in srgb, var(--red) 6%, transparent);
		border: 1px solid color-mix(in srgb, var(--red) 20%, transparent);
		border-radius: 6px;
	}

	@media (max-width: 768px) {
		.main { padding: 16px; }
	}
</style>
