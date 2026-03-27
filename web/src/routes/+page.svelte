<script lang="ts">
	import { onMount, tick } from 'svelte';
	import { agentColor } from '$lib/colors';
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

	// ── Mode icons ─────────────────────────────────────────────
	const MODE_ICONS: Record<string, string> = {
		debate: '🏛️',
		plan: '🧠',
		tech: '🔬',
	};

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

	// ── Launch debate ──────────────────────────────────────────
	function launchDebate() {
		if (!question.trim() || status === 'running' || status === 'judging') return;
		reset();
		status = 'running';

		const params = new URLSearchParams({
			question: question.trim(),
			mode: selectedMode,
			rounds: String(selectedRounds),
			unlimited: String(unlimited),
		});

		const evtSource = new EventSource(`/api/debate/stream?${params}`);

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
		});

		evtSource.addEventListener('done', (_e) => {
			status = 'done';
			evtSource.close();
			refreshTranscripts();
		});

		evtSource.onerror = () => {
			if (status === 'running' || status === 'judging') {
				// SSE connection closed naturally after done event
				if (verdict) {
					status = 'done';
				}
			}
			evtSource.close();
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
		});

		evtSource.addEventListener('done', (_e) => {
			status = 'done';
			evtSource.close();
			refreshTranscripts();
		});

		evtSource.onerror = () => {
			evtSource.close();
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
			if (status === 'done' && followupText.trim()) {
				sendFollowup();
			} else if (status === 'idle' || status === 'done' || status === 'error') {
				launchDebate();
			}
		}
	}

	// ── Derived ────────────────────────────────────────────────
	let modeList = $derived(Object.entries(modes));
	let currentModeInfo = $derived(modes[selectedMode]);
	let hasDebate = $derived(rounds.length > 0 || verdict);
	let isRunning = $derived(status === 'running' || status === 'judging');
</script>

<svelte:window on:keydown={onKeydown} />

<div class="app">
	<!-- Sidebar toggle (mobile) -->
	<button class="sidebar-toggle" onclick={() => (sidebarOpen = !sidebarOpen)}>
		{sidebarOpen ? '✕' : '☰'}
	</button>

	<!-- Sidebar -->
	<aside class="sidebar" class:open={sidebarOpen}>
		<div class="sidebar-header">
			<h2>Transcripts</h2>
			<button class="refresh-btn" onclick={refreshTranscripts} title="Refresh">↻</button>
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
				<p class="empty-msg">No transcripts yet.</p>
			{/each}
		</div>
	</aside>

	<!-- Main content -->
	<main class="main">
		{#if selectedTranscript}
			<!-- Transcript viewer -->
			<div class="transcript-viewer">
				<div class="transcript-viewer-header">
					<h2>{selectedTranscript.filename}</h2>
					<button class="close-btn" onclick={closeTranscript}>✕ Close</button>
				</div>
				<div class="transcript-content">
					<pre>{selectedTranscript.content}</pre>
				</div>
			</div>
		{:else}
			<!-- Header -->
			<div class="header">
				<h1 class="logo">
					<span class="logo-icon">⚔️</span>
					Agent Colosseum
				</h1>
				<p class="tagline">Multi-agent debate arena powered by Claude</p>
			</div>

			<!-- Controls -->
			<div class="controls">
				<div class="input-row">
					<input
						class="question-input"
						type="text"
						placeholder="What should your war council debate?"
						bind:value={question}
						disabled={isRunning}
					/>
					<button
						class="launch-btn"
						onclick={launchDebate}
						disabled={isRunning || !question.trim()}
					>
						{#if isRunning}
							<span class="spinner"></span>
							Running...
						{:else}
							Launch ⚡
						{/if}
					</button>
				</div>

				<div class="options-row">
					<div class="option-group">
						<span class="option-label">Mode</span>
						<div class="mode-selector">
							{#each modeList as [key, info]}
								<button
									class="mode-btn"
									class:active={selectedMode === key}
									onclick={() => (selectedMode = key)}
									disabled={isRunning}
									title={info.description}
								>
									{MODE_ICONS[key] || '🏛️'} {key}
								</button>
							{/each}
						</div>
					</div>
					<div class="option-group">
						<span class="option-label">Rounds</span>
						<div class="rounds-selector">
							{#each [3, 5] as n}
								<button
									class="round-btn"
									class:active={!unlimited && selectedRounds === n}
									onclick={() => { selectedRounds = n; unlimited = false; }}
									disabled={isRunning}
								>
									{n}
								</button>
							{/each}
							<button
								class="round-btn"
								class:active={unlimited}
								onclick={() => (unlimited = !unlimited)}
								disabled={isRunning}
							>
								∞
							</button>
						</div>
					</div>
				</div>

				{#if currentModeInfo}
					<div class="agents-preview">
						{#each Object.entries(currentModeInfo.agents) as [name, agent]}
							<span class="agent-badge" style="color: {agentColor(agent.color)}">
								{name}
							</span>
						{/each}
					</div>
				{/if}
			</div>

			<!-- Debate log -->
			{#if hasDebate || isRunning}
				<div class="debate-log" bind:this={debateLogEl}>
					{#each rounds as round}
						<div class="round-block">
							<div class="round-header">
								<span class="round-num">Round {round.round}</span>
								<span class="round-title">{round.title}</span>
							</div>
							{#if Object.keys(round.responses).length > 0}
								<div class="responses">
									{#each Object.entries(round.responses) as [agent, response]}
										<div class="response">
											<div class="agent-name" style="color: {agentColor(currentAgentColors[agent] || 'white')}">
												{agent}
											</div>
											<div class="agent-response">{response}</div>
										</div>
									{/each}
								</div>
							{:else if currentSpinner}
								<div class="loading-indicator">
									<span class="spinner"></span>
									<span>{currentSpinner}</span>
								</div>
							{/if}
						</div>
					{/each}

					{#each infoMessages as msg}
						<div class="info-message">{msg}</div>
					{/each}

					{#if status === 'judging' && !verdict}
						<div class="loading-indicator verdict-loading">
							<span class="spinner"></span>
							<span>Delivering verdict...</span>
						</div>
					{/if}

					{#if verdict}
						<div class="verdict-block">
							<div class="verdict-header">{verdictTitle || '⚖️ VERDICT'}</div>
							<div class="verdict-text">{verdict}</div>
						</div>
					{/if}

					{#each followupResponses as fu}
						<div class="followup-block">
							<div class="followup-question">Follow-up: {fu.question}</div>
							<div class="responses">
								{#each Object.entries(fu.responses) as [agent, response]}
									<div class="response">
										<div class="agent-name" style="color: {agentColor(currentAgentColors[agent] || 'white')}">
											{agent}
										</div>
										<div class="agent-response">{response}</div>
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
							class="followup-btn"
							onclick={sendFollowup}
							disabled={!followupText.trim()}
						>
							Ask →
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

	.sidebar {
		width: 280px;
		min-width: 280px;
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
		padding: 20px 16px 12px;
		border-bottom: 1px solid var(--border);
	}

	.sidebar-header h2 {
		font-size: 14px;
		font-weight: 600;
		color: var(--text-dim);
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}

	.refresh-btn {
		background: none;
		border: none;
		color: var(--text-dim);
		font-size: 18px;
		cursor: pointer;
		padding: 4px;
		border-radius: 4px;
		transition: all 0.15s;
	}
	.refresh-btn:hover {
		color: var(--text);
		background: var(--bg-hover);
	}

	.transcript-list {
		flex: 1;
		overflow-y: auto;
		padding: 8px;
	}

	.transcript-item {
		display: flex;
		flex-direction: column;
		gap: 2px;
		width: 100%;
		padding: 10px 12px;
		background: none;
		border: none;
		border-radius: var(--radius-sm);
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
	}
	.transcript-date {
		font-size: 11px;
		color: var(--text-muted);
		font-family: var(--font-mono);
	}

	.empty-msg {
		padding: 20px;
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
		padding: 24px 32px;
		gap: 20px;
	}

	/* ── Header ────────────────────────────────────── */
	.header {
		text-align: center;
		padding: 8px 0;
	}

	.logo {
		font-size: 28px;
		font-weight: 800;
		letter-spacing: -0.02em;
	}
	.logo-icon {
		font-size: 24px;
	}

	.tagline {
		color: var(--text-dim);
		font-size: 14px;
		margin-top: 4px;
	}

	/* ── Controls ──────────────────────────────────── */
	.controls {
		display: flex;
		flex-direction: column;
		gap: 12px;
	}

	.input-row {
		display: flex;
		gap: 10px;
	}

	.question-input {
		flex: 1;
		padding: 14px 18px;
		background: var(--bg-surface);
		border: 1px solid var(--border);
		border-radius: var(--radius);
		color: var(--text);
		font-size: 15px;
		font-family: var(--font-sans);
		outline: none;
		transition: border-color 0.2s, box-shadow 0.2s;
	}
	.question-input:focus {
		border-color: var(--accent);
		box-shadow: 0 0 0 3px var(--accent-glow);
	}
	.question-input::placeholder {
		color: var(--text-muted);
	}
	.question-input:disabled {
		opacity: 0.5;
	}

	.launch-btn {
		padding: 14px 24px;
		background: var(--accent);
		color: white;
		border: none;
		border-radius: var(--radius);
		font-size: 15px;
		font-weight: 600;
		font-family: var(--font-sans);
		cursor: pointer;
		transition: all 0.15s;
		display: flex;
		align-items: center;
		gap: 8px;
		white-space: nowrap;
	}
	.launch-btn:hover:not(:disabled) {
		filter: brightness(1.1);
		transform: translateY(-1px);
	}
	.launch-btn:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.options-row {
		display: flex;
		gap: 24px;
		align-items: center;
	}

	.option-group {
		display: flex;
		align-items: center;
		gap: 8px;
	}

	.option-label {
		font-size: 12px;
		font-weight: 600;
		color: var(--text-muted);
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}

	.mode-selector, .rounds-selector {
		display: flex;
		gap: 4px;
	}

	.mode-btn, .round-btn {
		padding: 6px 14px;
		background: var(--bg-surface);
		border: 1px solid var(--border);
		border-radius: var(--radius-sm);
		color: var(--text-dim);
		font-size: 13px;
		font-weight: 500;
		font-family: var(--font-sans);
		cursor: pointer;
		transition: all 0.15s;
		text-transform: capitalize;
	}
	.mode-btn:hover:not(:disabled), .round-btn:hover:not(:disabled) {
		background: var(--bg-hover);
		color: var(--text);
	}
	.mode-btn.active, .round-btn.active {
		background: var(--accent);
		border-color: var(--accent);
		color: white;
	}
	.mode-btn:disabled, .round-btn:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.agents-preview {
		display: flex;
		gap: 12px;
		flex-wrap: wrap;
	}

	.agent-badge {
		font-size: 12px;
		font-weight: 600;
		font-family: var(--font-mono);
		padding: 3px 10px;
		background: var(--bg-elevated);
		border-radius: 20px;
		border: 1px solid var(--border);
	}

	/* ── Debate log ────────────────────────────────── */
	.debate-log {
		flex: 1;
		overflow-y: auto;
		display: flex;
		flex-direction: column;
		gap: 16px;
		padding: 4px 0;
	}

	.round-block {
		display: flex;
		flex-direction: column;
		gap: 12px;
	}

	.round-header {
		display: flex;
		align-items: center;
		gap: 12px;
		padding: 8px 0;
		border-bottom: 1px solid var(--border);
	}

	.round-num {
		font-size: 11px;
		font-weight: 700;
		text-transform: uppercase;
		letter-spacing: 0.08em;
		color: var(--accent);
		font-family: var(--font-mono);
	}

	.round-title {
		font-size: 14px;
		font-weight: 600;
		color: var(--text);
	}

	.responses {
		display: flex;
		flex-direction: column;
		gap: 12px;
	}

	.response {
		background: var(--bg-surface);
		border: 1px solid var(--border);
		border-radius: var(--radius);
		padding: 14px 18px;
		transition: border-color 0.15s;
	}
	.response:hover {
		border-color: var(--border-accent);
	}

	.agent-name {
		font-size: 13px;
		font-weight: 700;
		font-family: var(--font-mono);
		margin-bottom: 6px;
	}

	.agent-response {
		font-size: 14px;
		line-height: 1.6;
		color: var(--text);
	}

	/* ── Loading ────────────────────────────────────── */
	.loading-indicator {
		display: flex;
		align-items: center;
		gap: 10px;
		padding: 12px 16px;
		color: var(--text-dim);
		font-size: 14px;
	}

	.spinner {
		display: inline-block;
		width: 16px;
		height: 16px;
		border: 2px solid var(--border);
		border-top-color: var(--accent);
		border-radius: 50%;
		animation: spin 0.8s linear infinite;
	}

	@keyframes spin {
		to { transform: rotate(360deg); }
	}

	/* ── Verdict ────────────────────────────────────── */
	.verdict-block {
		background: var(--bg-elevated);
		border: 2px solid var(--accent);
		border-radius: var(--radius);
		padding: 20px 24px;
		box-shadow: 0 0 24px var(--accent-glow);
	}

	.verdict-header {
		font-size: 14px;
		font-weight: 700;
		text-transform: uppercase;
		letter-spacing: 0.08em;
		color: var(--accent);
		margin-bottom: 12px;
		font-family: var(--font-mono);
	}

	.verdict-text {
		font-size: 15px;
		line-height: 1.7;
		color: var(--text);
	}

	/* ── Follow-up ──────────────────────────────────── */
	.followup-row {
		display: flex;
		gap: 10px;
		padding-top: 4px;
	}

	.followup-input {
		flex: 1;
		padding: 12px 16px;
		background: var(--bg-surface);
		border: 1px solid var(--border);
		border-radius: var(--radius);
		color: var(--text);
		font-size: 14px;
		font-family: var(--font-sans);
		outline: none;
		transition: border-color 0.2s, box-shadow 0.2s;
	}
	.followup-input:focus {
		border-color: var(--accent);
		box-shadow: 0 0 0 3px var(--accent-glow);
	}
	.followup-input::placeholder {
		color: var(--text-muted);
	}

	.followup-btn {
		padding: 12px 20px;
		background: var(--bg-elevated);
		border: 1px solid var(--border-accent);
		border-radius: var(--radius);
		color: var(--text);
		font-size: 14px;
		font-weight: 600;
		font-family: var(--font-sans);
		cursor: pointer;
		transition: all 0.15s;
		white-space: nowrap;
	}
	.followup-btn:hover:not(:disabled) {
		background: var(--accent);
		border-color: var(--accent);
		color: white;
	}
	.followup-btn:disabled {
		opacity: 0.4;
		cursor: not-allowed;
	}

	.followup-block {
		display: flex;
		flex-direction: column;
		gap: 12px;
	}

	.followup-question {
		font-size: 14px;
		font-weight: 600;
		color: var(--yellow);
		padding: 8px 0;
		border-bottom: 1px solid var(--border);
	}

	/* ── Info & Error ──────────────────────────────── */
	.info-message {
		font-size: 13px;
		font-style: italic;
		color: var(--text-dim);
		padding: 4px 0;
	}

	.error-message {
		font-size: 14px;
		color: var(--red);
		padding: 12px 16px;
		background: #ef6a6a11;
		border: 1px solid #ef6a6a33;
		border-radius: var(--radius-sm);
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
		padding-bottom: 16px;
		border-bottom: 1px solid var(--border);
	}

	.transcript-viewer-header h2 {
		font-size: 14px;
		font-weight: 600;
		color: var(--text-dim);
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.close-btn {
		padding: 6px 14px;
		background: var(--bg-surface);
		border: 1px solid var(--border);
		border-radius: var(--radius-sm);
		color: var(--text-dim);
		font-size: 13px;
		font-family: var(--font-sans);
		cursor: pointer;
		transition: all 0.15s;
		white-space: nowrap;
	}
	.close-btn:hover {
		background: var(--bg-hover);
		color: var(--text);
	}

	.transcript-content {
		flex: 1;
		overflow-y: auto;
		padding-top: 16px;
	}

	.transcript-content pre {
		font-family: var(--font-mono);
		font-size: 13px;
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
			box-shadow: 4px 0 24px #00000044;
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
			border-radius: var(--radius-sm);
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
			gap: 12px;
		}

		.input-row {
			flex-direction: column;
		}
	}
</style>
