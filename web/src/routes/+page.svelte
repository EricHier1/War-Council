<script lang="ts">
	import { onMount, onDestroy, tick } from 'svelte';
	import type { Modes, TranscriptEntry, RoundData, DebateStatus, Metrics, StructuredVerdict } from '$lib/types';

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
	let selectedTranscript: { filename: string; content: string; question?: string; mode?: string | null } | null = $state(null);

	let question = $state('');
	let selectedMode = $state('debate');
	let selectedRounds = $state(3);
	let unlimited = $state(false);
	let selectedModel = $state('sonnet');
	let repoPath = $state('');

	let status = $state<DebateStatus>('idle');
	let sessionId = $state('');
	let currentAgentColors: Record<string, string> = $state({});
	let rounds: RoundData[] = $state([]);
	let currentSpinner = $state('');
	let verdict = $state('');
	let verdictTitle = $state('');
	let structuredVerdict: StructuredVerdict | null = $state(null);
	let metrics: Metrics | null = $state(null);
	let currentRepo = $state<string | null>(null);
	let errorMessage = $state('');
	let infoMessages: string[] = $state([]);

	let followupText = $state('');
	let followupResponses: { question: string; responses: Record<string, string>; models?: Record<string, string> }[] = $state([]);

	let debateLogEl: HTMLElement | undefined = $state();
	let sidebarOpen = $state(false);
	let activeEventSource: EventSource | null = $state(null);

	let loading = $state(true);
	let loadError = $state('');
	let improving = $state(false);

	// ── Lifecycle ──────────────────────────────────────────────
	async function loadInitial() {
		loading = true;
		loadError = '';
		try {
			const [modesRes, transRes] = await Promise.all([
				fetch('/api/modes'),
				fetch('/api/transcripts'),
			]);
			if (!modesRes.ok || !transRes.ok) throw new Error('Backend returned an error');
			modes = await modesRes.json();
			transcripts = await transRes.json();
		} catch {
			loadError = 'Could not reach the backend. Make sure the server is running, then retry.';
		} finally {
			loading = false;
		}
	}

	onMount(loadInitial);

	onDestroy(() => activeEventSource?.close());

	// ── Helpers ────────────────────────────────────────────────
	async function scrollToBottom() {
		// Only auto-scroll if the user is already near the bottom, so it doesn't
		// yank them down while they're reading an earlier response.
		const el = debateLogEl;
		const nearBottom = !el || el.scrollHeight - el.scrollTop - el.clientHeight < 120;
		await tick();
		if (debateLogEl && nearBottom) debateLogEl.scrollTop = debateLogEl.scrollHeight;
	}

	function formatTokens(n: number): string {
		if (n >= 1000) return (n / 1000).toFixed(1).replace(/\.0$/, '') + 'k';
		return String(n);
	}

	async function refreshTranscripts() {
		try {
			const res = await fetch('/api/transcripts');
			if (res.ok) transcripts = await res.json();
		} catch {
			// Non-critical refresh; keep the existing list rather than crashing.
		}
	}

	function reset() {
		rounds = [];
		verdict = '';
		verdictTitle = '';
		structuredVerdict = null;
		metrics = null;
		currentRepo = null;
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

	// ── Improve prompt ─────────────────────────────────────────
	async function improvePrompt() {
		if (!question.trim() || improving || isRunning) return;
		improving = true;
		loadError = '';
		try {
			const res = await fetch('/api/improve-prompt', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ question: question.trim(), mode: selectedMode, model: selectedModel }),
			});
			if (!res.ok) throw new Error('improve failed');
			const data = await res.json();
			if (data.improved) question = data.improved;
		} catch {
			loadError = 'Could not improve the prompt. Make sure the backend is running.';
		} finally {
			improving = false;
		}
	}

	// ── Shared debate-stream handlers (used by launch + extend) ────
	function attachStreamHandlers(es: EventSource) {
		es.addEventListener('session', (e) => {
			const d = JSON.parse(e.data);
			sessionId = d.session_id;
			currentAgentColors = d.agents;
			currentRepo = d.repo ?? null;
		});
		es.addEventListener('round_start', (e) => {
			const d = JSON.parse(e.data);
			currentSpinner = d.spinner;
			rounds.push({ round: d.round, title: d.title, responses: {}, models: {} });
			scrollToBottom();
		});
		es.addEventListener('agent_response', (e) => {
			const d = JSON.parse(e.data);
			const idx = rounds.findIndex((r) => r.round === d.round);
			if (idx >= 0) {
				rounds[idx].responses[d.agent] = d.response;
				if (d.model) (rounds[idx].models ??= {})[d.agent] = d.model;
			}
			scrollToBottom();
		});
		es.addEventListener('judging', () => { status = 'judging'; currentSpinner = 'Delivering verdict...'; scrollToBottom(); });
		es.addEventListener('verdict', (e) => {
			const d = JSON.parse(e.data);
			verdict = d.verdict;
			verdictTitle = d.title;
			structuredVerdict = d.structured ?? null;
			currentSpinner = '';
			scrollToBottom();
		});
		es.addEventListener('metrics', (e) => { metrics = JSON.parse(e.data); });
		es.addEventListener('info', (e) => { infoMessages = [...infoMessages, JSON.parse(e.data).message]; scrollToBottom(); });
		es.addEventListener('server_error', (e) => {
			try { errorMessage = JSON.parse(e.data).message; } catch { errorMessage = 'The backend reported an error.'; }
			status = 'error'; currentSpinner = ''; es.close(); activeEventSource = null;
		});
		es.addEventListener('done', () => { status = 'done'; es.close(); activeEventSource = null; refreshTranscripts(); });
		// Native onerror fires only on transport failure (the done/server_error
		// handlers close the socket first), so treat it as a real connection drop.
		es.onerror = () => {
			es.close();
			if (activeEventSource === es) activeEventSource = null;
			if (status === 'running' || status === 'judging') {
				if (verdict) {
					status = 'done';
				} else {
					status = 'error';
					currentSpinner = '';
					errorMessage = 'Connection lost. The backend may have stopped — check it and retry.';
				}
			}
		};
	}

	// ── Launch ─────────────────────────────────────────────────
	function launchDebate() {
		if (!question.trim() || isRunning) return;
		activeEventSource?.close();
		reset();
		status = 'running';

		const params = new URLSearchParams({
			question: question.trim(),
			mode: selectedMode,
			rounds: String(selectedRounds),
			unlimited: String(unlimited),
			model: selectedModel,
		});
		if (repoPath.trim()) params.set('repo', repoPath.trim());

		const es = new EventSource(`/api/debate/stream?${params}`);
		activeEventSource = es;
		attachStreamHandlers(es);
	}

	// ── Extend (run more rounds on the existing debate) ─────────
	function extendDebate() {
		if (!sessionId || isRunning) return;
		activeEventSource?.close();
		errorMessage = '';
		status = 'running';
		currentSpinner = 'Continuing the debate...';

		const es = new EventSource(`/api/extend/stream?${new URLSearchParams({ session_id: sessionId, rounds: '2' })}`);
		activeEventSource = es;
		attachStreamHandlers(es);
	}

	// ── Follow-up ──────────────────────────────────────────────
	function sendFollowup() {
		if (!followupText.trim() || !sessionId || status !== 'done') return;
		activeEventSource?.close();
		const fq = followupText.trim();
		followupText = '';
		errorMessage = '';
		status = 'running';
		currentSpinner = 'Agents responding...';

		followupResponses = [...followupResponses, { question: fq, responses: {}, models: {} }];

		const es = new EventSource(`/api/followup/stream?${new URLSearchParams({ session_id: sessionId, followup: fq })}`);
		activeEventSource = es;

		es.addEventListener('followup_agent', (e) => {
			const d = JSON.parse(e.data);
			const last = followupResponses[followupResponses.length - 1];
			if (last) {
				last.responses[d.agent] = d.response;
				if (d.model) (last.models ??= {})[d.agent] = d.model;
			}
			currentSpinner = '';
			scrollToBottom();
		});
		es.addEventListener('metrics', (e) => { metrics = JSON.parse(e.data); });
		es.addEventListener('server_error', (e) => {
			try { errorMessage = JSON.parse(e.data).message; } catch { errorMessage = 'The backend reported an error.'; }
			currentSpinner = ''; status = 'done'; es.close(); activeEventSource = null;
		});
		es.addEventListener('done', () => { status = 'done'; es.close(); activeEventSource = null; refreshTranscripts(); });
		es.onerror = () => {
			es.close();
			if (activeEventSource === es) activeEventSource = null;
			if (status === 'running') {
				currentSpinner = '';
				status = 'done';
				if (!errorMessage) errorMessage = 'Connection lost during follow-up.';
			}
		};
	}

	// ── Transcript ─────────────────────────────────────────────
	async function viewTranscript(filename: string) {
		try {
			const res = await fetch(`/api/transcripts/${encodeURIComponent(filename)}`);
			if (!res.ok) throw new Error('not found');
			selectedTranscript = await res.json();
			sidebarOpen = false;
		} catch {
			loadError = `Could not load transcript "${filename}".`;
		}
	}

	// Re-run a saved transcript as a fresh debate with its original question/mode.
	function rerunTranscript(q: string, m: string | null) {
		selectedTranscript = null;
		question = q;
		if (m) selectedMode = m;
		launchDebate();
	}

	// ── Key handler ────────────────────────────────────────────
	function onKeydown(e: KeyboardEvent) {
		// Plain Enter submits; Shift+Enter inserts a newline in the textarea.
		if (e.key !== 'Enter' || e.shiftKey) return;
		const t = e.target as HTMLElement;
		if (t?.classList?.contains('followup-input') && followupText.trim()) { e.preventDefault(); sendFollowup(); }
		else if (t?.classList?.contains('question-input') && !isRunning && question.trim()) { e.preventDefault(); launchDebate(); }
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

		{#if loadError}
			<div class="load-banner" role="alert">
				<span>{loadError}</span>
				<button class="retry-btn" onclick={loadInitial}>Retry</button>
			</div>
		{/if}

		{#if loading}
			<p class="loading-message">Loading…</p>
		{:else if selectedTranscript}
			<TranscriptViewer
				transcript={selectedTranscript}
				onClose={() => (selectedTranscript = null)}
				onRerun={rerunTranscript}
			/>
		{:else}
			<div class="content" class:landing={!hasDebate && !isRunning}>
			<DebateControls
				bind:question
				bind:selectedMode
				bind:selectedRounds
				bind:unlimited
				bind:selectedModel
				bind:repoPath
				{modes}
				{isRunning}
				{hasDebate}
				{improving}
				onLaunch={launchDebate}
				onImprove={improvePrompt}
				onStop={stopDebate}
				onNewDebate={newDebate}
			/>

			<StatusBar
				spinner={currentSpinner}
				completedRounds={completedRoundCount}
				visible={isRunning && !!currentSpinner}
			/>

			{#if hasDebate || isRunning}
				<div class="debate-log" bind:this={debateLogEl} aria-live="polite">
					{#if currentRepo}
						<p class="repo-chip" title={currentRepo}>
							<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg>
							grounded in {currentRepo}
						</p>
					{/if}
					{#each rounds as round}
						<RoundBlock {round} agentColors={currentAgentColors} />
					{/each}

					{#each infoMessages as msg}
						<p class="info-message">{msg}</p>
					{/each}

					{#if verdict}
						<VerdictBlock {verdict} structured={structuredVerdict} title={verdictTitle || 'Verdict'} />
					{/if}

					{#if metrics}
						<p class="metrics-line">
							{(metrics.elapsed_ms / 1000).toFixed(1)}s
							· {formatTokens(metrics.input_tokens)} in / {formatTokens(metrics.output_tokens)} out
							· ${metrics.cost_usd.toFixed(3)}
						</p>
					{/if}

					{#each followupResponses as fu}
						<RoundBlock followup={fu} agentColors={currentAgentColors} isFollowup />
					{/each}

					{#if errorMessage}
						<p class="error-message">{errorMessage}</p>
					{/if}
				</div>

				{#if status === 'done' && sessionId}
					<div class="post-verdict">
						<button class="extend-btn" onclick={extendDebate} title="Run 2 more debate rounds, then re-judge">
							+ 2 more rounds
						</button>
						<FollowupInput bind:value={followupText} onSend={sendFollowup} disabled={!followupText.trim()} />
					</div>
				{/if}
			{/if}
			</div>
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
	.content {
		flex: 1;
		min-height: 0;
		display: flex;
		flex-direction: column;
		gap: 16px;
	}
	/* Pre-launch landing: center the controls in the available space. */
	.content.landing {
		justify-content: center;
		padding-bottom: 10vh;
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
	.metrics-line {
		font-size: 11px;
		color: var(--text-muted);
		font-family: var(--font-mono);
		padding: 2px 0;
	}
	.repo-chip {
		display: inline-flex;
		align-items: center;
		gap: 6px;
		align-self: flex-start;
		font-size: 11px;
		font-family: var(--font-mono);
		color: var(--text-dim);
		background: var(--bg-surface);
		border: 1px solid var(--border);
		border-radius: 5px;
		padding: 4px 10px;
		max-width: 100%;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.post-verdict {
		display: flex;
		flex-direction: column;
		gap: 8px;
		flex-shrink: 0;
	}
	.extend-btn {
		align-self: flex-start;
		padding: 6px 14px;
		background: var(--bg-elevated);
		border: 1px solid var(--border);
		border-radius: var(--radius-sm);
		color: var(--text-dim);
		font-size: 12px;
		font-weight: 500;
		font-family: var(--font-sans);
		cursor: pointer;
		transition: all 0.15s;
	}
	.extend-btn:hover {
		color: var(--accent);
		border-color: var(--border-accent);
	}
	.error-message {
		font-size: 13px;
		color: var(--red);
		padding: 10px 14px;
		background: color-mix(in srgb, var(--red) 6%, transparent);
		border: 1px solid color-mix(in srgb, var(--red) 20%, transparent);
		border-radius: 6px;
	}
	.load-banner {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 12px;
		font-size: 13px;
		color: var(--red);
		padding: 10px 14px;
		background: color-mix(in srgb, var(--red) 6%, transparent);
		border: 1px solid color-mix(in srgb, var(--red) 20%, transparent);
		border-radius: 6px;
		flex-shrink: 0;
	}
	.retry-btn {
		font-size: 12px;
		padding: 4px 12px;
		border: 1px solid color-mix(in srgb, var(--red) 35%, transparent);
		border-radius: 5px;
		background: transparent;
		color: var(--red);
		cursor: pointer;
		flex-shrink: 0;
	}
	.retry-btn:hover {
		background: color-mix(in srgb, var(--red) 12%, transparent);
	}
	.loading-message {
		font-size: 13px;
		color: var(--text-muted);
		font-family: var(--font-mono);
		padding: 8px 0;
	}

	@media (max-width: 768px) {
		.main { padding: 16px; }
	}
</style>
