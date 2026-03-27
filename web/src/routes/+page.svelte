<script lang="ts">
	import { onMount, tick } from 'svelte';
	import { agentColor } from '$lib/colors';
	import { renderMarkdown } from '$lib/markdown';
	import type { Modes, TranscriptEntry, RoundData, DebateStatus } from '$lib/types';

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
		if (debateLogEl) {
			debateLogEl.scrollTop = debateLogEl.scrollHeight;
		}
	}

	async function refreshTranscripts() {
		const res = await fetch('/api/transcripts');
		transcripts = await res.json();
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

	// ── Stop debate ────────────────────────────────────────────
	function stopDebate() {
		if (activeEventSource) {
			activeEventSource.close();
			activeEventSource = null;
		}
		currentSpinner = '';
		status = rounds.length > 0 ? 'done' : 'idle';
		infoMessages = [...infoMessages, 'Session stopped by user.'];
		refreshTranscripts();
	}

	// ── Launch debate ──────────────────────────────────────────
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

		const evtSource = new EventSource(`/api/debate/stream?${params}`);
		activeEventSource = evtSource;

		evtSource.addEventListener('session', (e) => {
			const data = JSON.parse(e.data);
			sessionId = data.session_id;
			currentAgentColors = data.agents;
		});

		evtSource.addEventListener('round_start', (e) => {
			const data = JSON.parse(e.data);
			currentSpinner = data.spinner;
			rounds.push({ round: data.round, title: data.title, responses: {} });
			rounds = rounds;
			scrollToBottom();
		});

		evtSource.addEventListener('round_responses', (e) => {
			const data = JSON.parse(e.data);
			const idx = rounds.findIndex((r) => r.round === data.round);
			if (idx >= 0) {
				rounds[idx].responses = data.responses;
				rounds = rounds;
			}
			currentSpinner = '';
			scrollToBottom();
		});

		evtSource.addEventListener('judging', (_e) => {
			status = 'judging';
			currentSpinner = 'Delivering verdict...';
			scrollToBottom();
		});

		evtSource.addEventListener('verdict', (e) => {
			const data = JSON.parse(e.data);
			verdict = data.verdict;
			verdictTitle = data.title;
			currentSpinner = '';
			scrollToBottom();
		});

		evtSource.addEventListener('info', (e) => {
			const data = JSON.parse(e.data);
			infoMessages = [...infoMessages, data.message];
			scrollToBottom();
		});

		evtSource.addEventListener('error', (e) => {
			try {
				const data = JSON.parse(e.data);
				errorMessage = data.message;
			} catch {
				errorMessage = 'Connection lost';
			}
			status = 'error';
			currentSpinner = '';
			evtSource.close();
			activeEventSource = null;
		});

		evtSource.addEventListener('done', (_e) => {
			status = 'done';
			evtSource.close();
			activeEventSource = null;
			refreshTranscripts();
		});

		evtSource.onerror = () => {
			if (status === 'running' || status === 'judging') {
				if (verdict) {
					status = 'done';
				}
			}
			evtSource.close();
			activeEventSource = null;
		};
	}

	// ── Follow-up ──────────────────────────────────────────────
	function sendFollowup() {
		if (!followupText.trim() || !sessionId || status !== 'done') return;
		const fq = followupText.trim();
		followupText = '';
		status = 'running';
		currentSpinner = 'Agents responding...';

		const params = new URLSearchParams({
			session_id: sessionId,
			followup: fq,
		});

		const evtSource = new EventSource(`/api/followup/stream?${params}`);
		activeEventSource = evtSource;

		evtSource.addEventListener('followup_responses', (e) => {
			const data = JSON.parse(e.data);
			followupResponses = [...followupResponses, { question: fq, responses: data.responses }];
			currentSpinner = '';
			scrollToBottom();
		});

		evtSource.addEventListener('error', (e) => {
			try {
				const data = JSON.parse(e.data);
				errorMessage = data.message;
			} catch {
				errorMessage = 'Connection lost';
			}
			currentSpinner = '';
			status = 'done';
			evtSource.close();
			activeEventSource = null;
		});

		evtSource.addEventListener('done', (_e) => {
			status = 'done';
			evtSource.close();
			activeEventSource = null;
			refreshTranscripts();
		});

		evtSource.onerror = () => {
			evtSource.close();
			activeEventSource = null;
			status = 'done';
		};
	}

	// ── View transcript ────────────────────────────────────────
	async function viewTranscript(filename: string) {
		const res = await fetch(`/api/transcripts/${filename}`);
		const data = await res.json();
		if (!data.error) {
			selectedTranscript = data;
			sidebarOpen = false;
		}
	}

	function closeTranscript() {
		selectedTranscript = null;
	}

	// ── Key handler ────────────────────────────────────────────
	function onKeydown(e: KeyboardEvent) {
		if (e.key === 'Enter' && !e.shiftKey) {
			const target = e.target as HTMLElement;
			if (target?.classList?.contains('followup-input') && followupText.trim()) {
				sendFollowup();
			} else if (target?.classList?.contains('question-input') && (status === 'idle' || status === 'done' || status === 'error')) {
				launchDebate();
			}
		}
	}

	// ── Derived ────────────────────────────────────────────────
	let modeList = $derived(Object.entries(modes));
	let currentModeInfo = $derived(modes[selectedMode]);
	let hasDebate = $derived(rounds.length > 0 || verdict);
	let isRunning = $derived(status === 'running' || status === 'judging');
	let completedRoundCount = $derived(rounds.filter(r => Object.keys(r.responses).length > 0).length);
</script>

<svelte:window on:keydown={onKeydown} />

<div class="app">
	<!-- Sidebar toggle (mobile) -->
	<button class="sidebar-toggle" onclick={() => (sidebarOpen = !sidebarOpen)}>
		{sidebarOpen ? '\u2715' : '\u2630'}
	</button>

	<!-- Sidebar -->
	<aside class="sidebar" class:open={sidebarOpen}>
		<div class="sidebar-header">
			<h2>History</h2>
			<button class="icon-btn" onclick={refreshTranscripts} title="Refresh">
				<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 2v6h-6"/><path d="M3 12a9 9 0 0 1 15-6.7L21 8"/><path d="M3 22v-6h6"/><path d="M21 12a9 9 0 0 1-15 6.7L3 16"/></svg>
			</button>
		</div>
		<div class="transcript-list">
			{#each transcripts as t}
				<button
					class="transcript-item"
					onclick={() => viewTranscript(t.filename)}
				>
					<span class="transcript-name">{t.stem.split('_').slice(1).join(' ').replaceAll('-', ' ')}</span>
					<span class="transcript-date">{t.stem.split('_')[0]}</span>
				</button>
			{:else}
				<p class="empty-msg">No sessions yet</p>
			{/each}
		</div>
	</aside>

	<!-- Main content -->
	<main class="main">
		{#if selectedTranscript}
			<div class="transcript-viewer">
				<div class="transcript-viewer-header">
					<h2>{selectedTranscript.filename}</h2>
					<button class="btn-secondary btn-sm" onclick={closeTranscript}>Close</button>
				</div>
				<div class="transcript-content">
					<pre>{selectedTranscript.content}</pre>
				</div>
			</div>
		{:else}
			<!-- Header — compact when debate is active -->
			{#if !hasDebate && !isRunning}
				<div class="header">
					<h1 class="logo">Agent Colosseum</h1>
					<p class="tagline">Multi-agent debate arena powered by Claude</p>
				</div>
			{/if}

			<!-- Controls -->
			<div class="controls" class:compact={hasDebate || isRunning}>
				<div class="input-row">
					<input
						class="question-input"
						type="text"
						placeholder="Enter a question or topic to debate..."
						bind:value={question}
						disabled={isRunning}
					/>
					{#if isRunning}
						<button class="stop-btn" onclick={stopDebate}>
							<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><rect x="4" y="4" width="16" height="16" rx="2"/></svg>
							Stop
						</button>
					{:else}
						<button
							class="launch-btn"
							onclick={launchDebate}
							disabled={!question.trim()}
						>
							Launch
						</button>
					{/if}
				</div>

				<div class="options-row">
					<div class="option-group">
						<span class="option-label">Mode</span>
						<div class="segmented-control">
							{#each modeList as [key, info]}
								<button
									class="seg-btn"
									class:active={selectedMode === key}
									onclick={() => (selectedMode = key)}
									disabled={isRunning}
									title={info.description}
								>
									{key}
								</button>
							{/each}
						</div>
					</div>
					<div class="option-group">
						<span class="option-label">Rounds</span>
						<div class="segmented-control">
							{#each [3, 5] as n}
								<button
									class="seg-btn"
									class:active={!unlimited && selectedRounds === n}
									onclick={() => { selectedRounds = n; unlimited = false; }}
									disabled={isRunning}
								>
									{n}
								</button>
							{/each}
							<button
								class="seg-btn"
								class:active={unlimited}
								onclick={() => (unlimited = !unlimited)}
								disabled={isRunning}
							>
								Unlimited
							</button>
						</div>
					</div>

					{#if currentModeInfo && !hasDebate && !isRunning}
						<div class="agents-preview">
							{#each Object.entries(currentModeInfo.agents) as [name, agent]}
								<span class="agent-tag" style="--agent-color: {agentColor(agent.color)}">
									{name}
								</span>
							{/each}
						</div>
					{/if}
				</div>
			</div>

			<!-- Status bar when running -->
			{#if isRunning && currentSpinner}
				<div class="status-bar">
					<div class="pulse"></div>
					<span>{currentSpinner}</span>
					{#if completedRoundCount > 0}
						<span class="status-meta">
							{completedRoundCount} round{completedRoundCount !== 1 ? 's' : ''} complete
						</span>
					{/if}
				</div>
			{/if}

			<!-- Debate log -->
			{#if hasDebate || isRunning}
				<div class="debate-log" bind:this={debateLogEl}>
					{#each rounds as round}
						<div class="round-block">
							<div class="round-header">
								<div class="round-label">
									<span class="round-num">Round {round.round}</span>
									<span class="round-divider">/</span>
									<span class="round-title">{round.title}</span>
								</div>
							</div>
							{#if Object.keys(round.responses).length > 0}
								<div class="responses">
									{#each Object.entries(round.responses) as [agent, response]}
										<div class="response" style="--agent-color: {agentColor(currentAgentColors[agent] || 'white')}">
											<div class="agent-name">
												{agent}
											</div>
											<div class="agent-response prose">{@html renderMarkdown(response)}</div>
										</div>
									{/each}
								</div>
							{/if}
						</div>
					{/each}

					{#each infoMessages as msg}
						<div class="info-message">{msg}</div>
					{/each}

					{#if verdict}
						<div class="verdict-block">
							<div class="verdict-header">Verdict</div>
							<div class="verdict-text prose">{@html renderMarkdown(verdict)}</div>
						</div>
					{/if}

					{#each followupResponses as fu}
						<div class="round-block">
							<div class="round-header">
								<div class="round-label">
									<span class="round-num">Follow-up</span>
									<span class="round-divider">/</span>
									<span class="round-title">{fu.question}</span>
								</div>
							</div>
							<div class="responses">
								{#each Object.entries(fu.responses) as [agent, response]}
									<div class="response" style="--agent-color: {agentColor(currentAgentColors[agent] || 'white')}">
										<div class="agent-name">
											{agent}
										</div>
										<div class="agent-response prose">{@html renderMarkdown(response)}</div>
									</div>
								{/each}
							</div>
						</div>
					{/each}

					{#if errorMessage}
						<div class="error-message">{errorMessage}</div>
					{/if}
				</div>

				<!-- Follow-up input -->
				{#if status === 'done' && sessionId}
					<div class="followup-row">
						<input
							class="followup-input"
							type="text"
							placeholder="Ask a follow-up question..."
							bind:value={followupText}
						/>
						<button
							class="btn-secondary"
							onclick={sendFollowup}
							disabled={!followupText.trim()}
						>
							Send
						</button>
					</div>
				{/if}
			{/if}
		{/if}
	</main>
</div>

<style>
	/* ── Layout ────────────────────────────────────── */
	.app {
		display: flex;
		height: 100vh;
		overflow: hidden;
	}

	/* ── Sidebar ───────────────────────────────────── */
	.sidebar {
		width: 260px;
		min-width: 260px;
		background: var(--bg-surface);
		border-right: 1px solid var(--border);
		display: flex;
		flex-direction: column;
		overflow: hidden;
	}

	.sidebar-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 16px 16px 12px;
		border-bottom: 1px solid var(--border);
	}

	.sidebar-header h2 {
		font-size: 11px;
		font-weight: 600;
		color: var(--text-muted);
		text-transform: uppercase;
		letter-spacing: 0.08em;
	}

	.icon-btn {
		background: none;
		border: none;
		color: var(--text-muted);
		cursor: pointer;
		padding: 4px;
		border-radius: 4px;
		display: flex;
		align-items: center;
		transition: color 0.15s;
	}
	.icon-btn:hover {
		color: var(--text);
	}

	.transcript-list {
		flex: 1;
		overflow-y: auto;
		padding: 6px;
	}

	.transcript-item {
		display: flex;
		flex-direction: column;
		gap: 2px;
		width: 100%;
		padding: 8px 10px;
		background: none;
		border: none;
		border-radius: 6px;
		color: var(--text);
		cursor: pointer;
		text-align: left;
		transition: background 0.15s;
	}
	.transcript-item:hover {
		background: var(--bg-hover);
	}
	.transcript-name {
		font-size: 13px;
		font-weight: 500;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
		line-height: 1.4;
	}
	.transcript-date {
		font-size: 11px;
		color: var(--text-muted);
		font-family: var(--font-mono);
	}

	.empty-msg {
		padding: 24px 16px;
		text-align: center;
		color: var(--text-muted);
		font-size: 13px;
	}

	.sidebar-toggle {
		display: none;
	}

	/* ── Main ──────────────────────────────────────── */
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
	}

	/* ── Header ────────────────────────────────────── */
	.header {
		text-align: center;
		padding: 24px 0 8px;
	}

	.logo {
		font-size: 22px;
		font-weight: 700;
		letter-spacing: -0.03em;
		color: var(--text);
	}

	.tagline {
		color: var(--text-muted);
		font-size: 13px;
		margin-top: 4px;
		font-weight: 400;
	}

	/* ── Controls ──────────────────────────────────── */
	.controls {
		display: flex;
		flex-direction: column;
		gap: 12px;
	}
	.controls.compact {
		gap: 10px;
	}

	.input-row {
		display: flex;
		gap: 8px;
	}

	.question-input {
		flex: 1;
		padding: 11px 16px;
		background: var(--bg-surface);
		border: 1px solid var(--border);
		border-radius: var(--radius-sm);
		color: var(--text);
		font-size: 14px;
		font-family: var(--font-sans);
		outline: none;
		transition: border-color 0.2s, box-shadow 0.2s;
	}
	.question-input:focus {
		border-color: var(--accent);
		box-shadow: 0 0 0 2px var(--accent-glow);
	}
	.question-input::placeholder {
		color: var(--text-muted);
	}
	.question-input:disabled {
		opacity: 0.5;
	}

	.launch-btn {
		padding: 11px 22px;
		background: var(--accent);
		color: white;
		border: none;
		border-radius: var(--radius-sm);
		font-size: 14px;
		font-weight: 600;
		font-family: var(--font-sans);
		cursor: pointer;
		transition: all 0.15s;
		white-space: nowrap;
	}
	.launch-btn:hover:not(:disabled) {
		filter: brightness(1.1);
	}
	.launch-btn:disabled {
		opacity: 0.35;
		cursor: not-allowed;
	}

	.stop-btn {
		padding: 11px 20px;
		background: transparent;
		color: var(--red);
		border: 1px solid var(--red);
		border-radius: var(--radius-sm);
		font-size: 14px;
		font-weight: 600;
		font-family: var(--font-sans);
		cursor: pointer;
		transition: all 0.15s;
		white-space: nowrap;
		display: flex;
		align-items: center;
		gap: 6px;
	}
	.stop-btn:hover {
		background: var(--red);
		color: white;
	}

	.options-row {
		display: flex;
		gap: 20px;
		align-items: center;
		flex-wrap: wrap;
	}

	.option-group {
		display: flex;
		align-items: center;
		gap: 8px;
	}

	.option-label {
		font-size: 11px;
		font-weight: 600;
		color: var(--text-muted);
		text-transform: uppercase;
		letter-spacing: 0.06em;
	}

	.segmented-control {
		display: flex;
		background: var(--bg-surface);
		border: 1px solid var(--border);
		border-radius: 6px;
		overflow: hidden;
	}

	.seg-btn {
		padding: 5px 14px;
		background: transparent;
		border: none;
		border-right: 1px solid var(--border);
		color: var(--text-dim);
		font-size: 12px;
		font-weight: 500;
		font-family: var(--font-sans);
		cursor: pointer;
		transition: all 0.15s;
		text-transform: capitalize;
	}
	.seg-btn:last-child {
		border-right: none;
	}
	.seg-btn:hover:not(:disabled):not(.active) {
		background: var(--bg-hover);
		color: var(--text);
	}
	.seg-btn.active {
		background: var(--accent);
		color: white;
	}
	.seg-btn:disabled {
		opacity: 0.4;
		cursor: not-allowed;
	}

	.agents-preview {
		display: flex;
		gap: 6px;
		flex-wrap: wrap;
		margin-left: auto;
	}

	.agent-tag {
		font-size: 11px;
		font-weight: 500;
		font-family: var(--font-mono);
		padding: 3px 8px;
		color: var(--agent-color);
		background: color-mix(in srgb, var(--agent-color) 8%, transparent);
		border-radius: 4px;
	}

	/* ── Status bar ─────────────────────────────────── */
	.status-bar {
		display: flex;
		align-items: center;
		gap: 10px;
		padding: 8px 0;
		font-size: 13px;
		color: var(--text-dim);
	}

	.pulse {
		width: 8px;
		height: 8px;
		background: var(--accent);
		border-radius: 50%;
		animation: pulse-anim 1.5s ease-in-out infinite;
	}

	@keyframes pulse-anim {
		0%, 100% { opacity: 1; }
		50% { opacity: 0.3; }
	}

	.status-meta {
		margin-left: auto;
		font-family: var(--font-mono);
		font-size: 11px;
		color: var(--text-muted);
	}

	/* ── Debate log ────────────────────────────────── */
	.debate-log {
		flex: 1;
		overflow-y: auto;
		display: flex;
		flex-direction: column;
		gap: 24px;
		padding: 4px 0 16px;
	}

	.round-block {
		display: flex;
		flex-direction: column;
		gap: 10px;
	}

	.round-header {
		padding: 4px 0;
	}

	.round-label {
		display: flex;
		align-items: center;
		gap: 8px;
	}

	.round-num {
		font-size: 11px;
		font-weight: 700;
		text-transform: uppercase;
		letter-spacing: 0.06em;
		color: var(--accent);
		font-family: var(--font-mono);
	}

	.round-divider {
		color: var(--border-accent);
		font-size: 12px;
	}

	.round-title {
		font-size: 13px;
		font-weight: 500;
		color: var(--text-dim);
	}

	.responses {
		display: flex;
		flex-direction: column;
		gap: 8px;
	}

	.response {
		background: var(--bg-surface);
		border: 1px solid var(--border);
		border-left: 3px solid var(--agent-color, var(--border));
		border-radius: 6px;
		padding: 14px 16px;
		transition: border-color 0.15s;
	}
	.response:hover {
		border-color: var(--border-accent);
		border-left-color: var(--agent-color, var(--border-accent));
	}

	.agent-name {
		font-size: 12px;
		font-weight: 600;
		font-family: var(--font-mono);
		margin-bottom: 6px;
		color: var(--agent-color, var(--text));
		text-transform: uppercase;
		letter-spacing: 0.04em;
	}

	.agent-response {
		font-size: 14px;
		line-height: 1.65;
		color: var(--text);
	}

	/* ── Prose (markdown content) ───────────────────── */
	.prose :global(p) {
		margin: 0 0 0.6em;
	}
	.prose :global(p:last-child) {
		margin-bottom: 0;
	}
	.prose :global(strong) {
		font-weight: 600;
		color: var(--text);
	}
	.prose :global(em) {
		font-style: italic;
	}
	.prose :global(h1),
	.prose :global(h2),
	.prose :global(h3),
	.prose :global(h4) {
		font-weight: 600;
		color: var(--text);
		margin: 0.8em 0 0.4em;
		line-height: 1.3;
	}
	.prose :global(h1) { font-size: 1.2em; }
	.prose :global(h2) { font-size: 1.1em; }
	.prose :global(h3) { font-size: 1.05em; }
	.prose :global(h4) { font-size: 1em; }
	.prose :global(ul),
	.prose :global(ol) {
		margin: 0.4em 0 0.6em;
		padding-left: 1.5em;
	}
	.prose :global(li) {
		margin: 0.2em 0;
	}
	.prose :global(li > ul),
	.prose :global(li > ol) {
		margin: 0.1em 0;
	}
	.prose :global(blockquote) {
		border-left: 3px solid var(--border-accent);
		padding: 0.3em 0 0.3em 1em;
		margin: 0.5em 0;
		color: var(--text-dim);
	}
	.prose :global(a) {
		color: var(--accent);
		text-decoration: none;
	}
	.prose :global(a:hover) {
		text-decoration: underline;
	}
	.prose :global(hr) {
		border: none;
		border-top: 1px solid var(--border);
		margin: 0.8em 0;
	}
	.prose :global(table) {
		width: 100%;
		border-collapse: collapse;
		margin: 0.6em 0;
		font-size: 0.9em;
	}
	.prose :global(th),
	.prose :global(td) {
		border: 1px solid var(--border);
		padding: 6px 10px;
		text-align: left;
	}
	.prose :global(th) {
		background: var(--bg-elevated);
		font-weight: 600;
	}

	/* Inline code */
	.prose :global(code) {
		font-family: var(--font-mono);
		font-size: 0.88em;
		background: var(--bg-elevated);
		border: 1px solid var(--border);
		border-radius: 4px;
		padding: 0.15em 0.4em;
	}

	/* Code blocks */
	.prose :global(.code-block) {
		margin: 0.6em 0;
		border: 1px solid var(--border);
		border-radius: 6px;
		overflow: hidden;
		background: var(--bg);
	}
	.prose :global(.code-header) {
		font-family: var(--font-mono);
		font-size: 11px;
		color: var(--text-muted);
		padding: 4px 12px;
		background: var(--bg-surface);
		border-bottom: 1px solid var(--border);
		min-height: 4px;
	}
	.prose :global(.code-header:empty) {
		padding: 0;
		border-bottom: none;
		min-height: 0;
	}
	.prose :global(.code-block pre) {
		margin: 0;
		padding: 12px 14px;
		overflow-x: auto;
	}
	.prose :global(.code-block code) {
		font-family: var(--font-mono);
		font-size: 13px;
		line-height: 1.55;
		background: none;
		border: none;
		border-radius: 0;
		padding: 0;
	}

	/* highlight.js token colors (dark theme) */
	.prose :global(.hljs-keyword),
	.prose :global(.hljs-selector-tag),
	.prose :global(.hljs-built_in) {
		color: var(--magenta);
	}
	.prose :global(.hljs-string),
	.prose :global(.hljs-attr) {
		color: var(--green);
	}
	.prose :global(.hljs-number),
	.prose :global(.hljs-literal) {
		color: var(--orange);
	}
	.prose :global(.hljs-comment),
	.prose :global(.hljs-doctag) {
		color: var(--text-muted);
		font-style: italic;
	}
	.prose :global(.hljs-type),
	.prose :global(.hljs-class .hljs-title),
	.prose :global(.hljs-title) {
		color: var(--yellow);
	}
	.prose :global(.hljs-function) {
		color: var(--blue);
	}
	.prose :global(.hljs-variable),
	.prose :global(.hljs-template-variable) {
		color: var(--cyan);
	}
	.prose :global(.hljs-params) {
		color: var(--text);
	}
	.prose :global(.hljs-meta) {
		color: var(--text-dim);
	}
	.prose :global(.hljs-punctuation) {
		color: var(--text-dim);
	}

	/* ── Verdict ────────────────────────────────────── */
	.verdict-block {
		background: var(--bg-elevated);
		border: 1px solid var(--accent);
		border-left: 4px solid var(--accent);
		border-radius: 6px;
		padding: 20px 24px;
	}

	.verdict-header {
		font-size: 11px;
		font-weight: 700;
		text-transform: uppercase;
		letter-spacing: 0.1em;
		color: var(--accent);
		margin-bottom: 12px;
		font-family: var(--font-mono);
	}

	.verdict-text {
		font-size: 14px;
		line-height: 1.7;
		color: var(--text);
	}

	/* ── Follow-up ──────────────────────────────────── */
	.followup-row {
		display: flex;
		gap: 8px;
		padding-top: 4px;
		flex-shrink: 0;
	}

	.followup-input {
		flex: 1;
		padding: 10px 14px;
		background: var(--bg-surface);
		border: 1px solid var(--border);
		border-radius: 6px;
		color: var(--text);
		font-size: 13px;
		font-family: var(--font-sans);
		outline: none;
		transition: border-color 0.2s, box-shadow 0.2s;
	}
	.followup-input:focus {
		border-color: var(--accent);
		box-shadow: 0 0 0 2px var(--accent-glow);
	}
	.followup-input::placeholder {
		color: var(--text-muted);
	}

	.btn-secondary {
		padding: 10px 18px;
		background: var(--bg-elevated);
		border: 1px solid var(--border);
		border-radius: 6px;
		color: var(--text);
		font-size: 13px;
		font-weight: 500;
		font-family: var(--font-sans);
		cursor: pointer;
		transition: all 0.15s;
		white-space: nowrap;
	}
	.btn-secondary:hover:not(:disabled) {
		background: var(--bg-hover);
		border-color: var(--border-accent);
	}
	.btn-secondary:disabled {
		opacity: 0.35;
		cursor: not-allowed;
	}

	.btn-sm {
		padding: 6px 14px;
		font-size: 12px;
	}

	/* ── Info & Error ──────────────────────────────── */
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

	/* ── Transcript viewer ─────────────────────────── */
	.transcript-viewer {
		display: flex;
		flex-direction: column;
		height: 100%;
		overflow: hidden;
	}

	.transcript-viewer-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding-bottom: 12px;
		border-bottom: 1px solid var(--border);
	}

	.transcript-viewer-header h2 {
		font-size: 13px;
		font-weight: 500;
		color: var(--text-dim);
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
		font-family: var(--font-mono);
	}

	.transcript-content {
		flex: 1;
		overflow-y: auto;
		padding-top: 16px;
	}

	.transcript-content pre {
		font-family: var(--font-mono);
		font-size: 12px;
		line-height: 1.7;
		white-space: pre-wrap;
		word-wrap: break-word;
		color: var(--text);
	}

	/* ── Mobile ────────────────────────────────────── */
	@media (max-width: 768px) {
		.sidebar {
			position: fixed;
			left: 0;
			top: 0;
			bottom: 0;
			z-index: 100;
			transform: translateX(-100%);
			transition: transform 0.2s ease;
			box-shadow: 4px 0 24px #00000066;
		}
		.sidebar.open {
			transform: translateX(0);
		}

		.sidebar-toggle {
			display: flex;
			align-items: center;
			justify-content: center;
			position: fixed;
			top: 12px;
			left: 12px;
			z-index: 101;
			width: 36px;
			height: 36px;
			background: var(--bg-elevated);
			border: 1px solid var(--border);
			border-radius: 6px;
			color: var(--text);
			font-size: 18px;
			cursor: pointer;
		}

		.main {
			padding: 16px;
		}

		.options-row {
			flex-direction: column;
			align-items: flex-start;
			gap: 10px;
		}

		.agents-preview {
			margin-left: 0;
		}

		.input-row {
			flex-direction: column;
		}
	}
</style>
