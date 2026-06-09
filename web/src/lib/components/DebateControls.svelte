<script lang="ts">
	import { onMount } from 'svelte';
	import { agentColor } from '$lib/colors';
	import { pickSuggestions } from '$lib/suggestions';
	import type { Modes } from '$lib/types';

	let {
		question = $bindable(),
		selectedMode = $bindable(),
		selectedRounds = $bindable(),
		unlimited = $bindable(),
		selectedModel = $bindable(),
		repoPath = $bindable(),
		modes,
		isRunning,
		hasDebate,
		improving,
		onLaunch,
		onImprove,
		onStop,
		onNewDebate,
	}: {
		question: string;
		selectedMode: string;
		selectedRounds: number;
		unlimited: boolean;
		selectedModel: string;
		repoPath: string;
		modes: Modes;
		isRunning: boolean;
		hasDebate: boolean;
		improving: boolean;
		onLaunch: () => void;
		onImprove: () => void;
		onStop: () => void;
		onNewDebate: () => void;
	} = $props();

	let modeList = $derived(Object.entries(modes));
	let currentModeInfo = $derived(modes[selectedMode]);

	const MODEL_OPTIONS = [
		{ key: 'haiku', label: 'Haiku', hint: 'Fastest & cheapest' },
		{ key: 'sonnet', label: 'Sonnet', hint: 'Balanced (default)' },
		{ key: 'opus', label: 'Opus', hint: 'Most capable' },
		{ key: 'fable', label: 'Fable', hint: 'Newest (Fable 5)' },
		{ key: 'diverse', label: 'Diverse', hint: 'Mixed Claude tiers per agent' },
	];

	let textareaEl: HTMLTextAreaElement | undefined = $state();

	// Picked client-side (onMount) to avoid an SSR/hydration mismatch.
	let suggestions = $state<string[]>([]);
	let suggestionsHidden = $state(false);

	onMount(() => {
		suggestions = pickSuggestions(4);
		suggestionsHidden = localStorage.getItem('suggestionsHidden') === 'true';
	});

	function useSuggestion(s: string) {
		question = s;
		textareaEl?.focus();
	}

	function shuffleSuggestions() {
		suggestions = pickSuggestions(4);
	}

	function setSuggestionsHidden(hidden: boolean) {
		suggestionsHidden = hidden;
		localStorage.setItem('suggestionsHidden', String(hidden));
	}

	// Grow the prompt box to fit its content (re-runs on typing and on
	// programmatic changes like Improve / New, since it reads `question`).
	$effect(() => {
		question;
		if (textareaEl) {
			textareaEl.style.height = 'auto';
			textareaEl.style.height = `${textareaEl.scrollHeight}px`;
		}
	});
</script>

{#if !hasDebate && !isRunning}
	<div class="header">
		<h1 class="logo">Agent Colosseum</h1>
		<p class="tagline">Multi-agent debate arena powered by Claude</p>
	</div>
{/if}

<div class="controls" class:compact={hasDebate || isRunning}>
	<div class="input-row">
		<textarea
			class="question-input"
			rows="1"
			placeholder="Enter a question or topic to debate..."
			bind:this={textareaEl}
			bind:value={question}
			disabled={isRunning || improving}
		></textarea>
		{#if isRunning}
			<button class="stop-btn" onclick={onStop}>
				<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><rect x="4" y="4" width="16" height="16" rx="2"/></svg>
				Stop
			</button>
		{:else}
			{#if hasDebate}
				<button class="new-btn" onclick={onNewDebate}>New</button>
			{/if}
			<button
				class="improve-btn"
				onclick={onImprove}
				disabled={!question.trim() || improving}
				title="Rewrite your prompt to be sharper and more debatable"
			>
				{#if improving}
					<span class="spinner" aria-hidden="true"></span>
					Improving…
				{:else}
					<svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M12 2l2.3 6.4 6.4 2.3-6.4 2.3L12 19.4l-2.3-6.4L3.3 10.7l6.4-2.3z"/></svg>
					Improve
				{/if}
			</button>
			<button
				class="launch-btn"
				onclick={onLaunch}
				disabled={!question.trim() || improving}
				title={!question.trim() ? 'Enter a question first' : 'Start the debate'}
			>
				Launch
			</button>
		{/if}
	</div>

	{#if !hasDebate && !isRunning}
		<div class="repo-row">
			<svg class="repo-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg>
			<input
				class="repo-input"
				type="text"
				placeholder="Optional: /path/to/repo — agents will read the codebase to ground the debate"
				bind:value={repoPath}
				disabled={improving}
			/>
			{#if repoPath.trim()}
				<button class="repo-clear" onclick={() => (repoPath = '')} title="Clear repo path" aria-label="Clear repo path">✕</button>
			{/if}
		</div>
		<p class="kbd-hint">
			<kbd>Enter</kbd> to launch · <kbd>Shift</kbd>+<kbd>Enter</kbd> for a new line
		</p>
	{/if}

	{#if !hasDebate && !isRunning && !question.trim()}
		{#if !suggestionsHidden && suggestions.length}
			<div class="suggestions">
				<div class="suggestions-head">
					<span class="suggestions-label">Try one of these</span>
					<div class="suggestions-actions">
						<button
							class="suggestions-shuffle"
							onclick={shuffleSuggestions}
							title="Show different suggestions"
							aria-label="Show different suggestions"
						>
							<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M21 2v6h-6"/><path d="M3 12a9 9 0 0 1 15-6.7L21 8"/><path d="M3 22v-6h6"/><path d="M21 12a9 9 0 0 1-15 6.7L3 16"/></svg>
							Shuffle
						</button>
						<button
							class="suggestions-hide"
							onclick={() => setSuggestionsHidden(true)}
							title="Hide suggestions"
							aria-label="Hide suggestions"
						>
							<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M18 6 6 18M6 6l12 12"/></svg>
						</button>
					</div>
				</div>
				<div class="suggestion-list">
					{#each suggestions as s}
						<button class="suggestion-item" onclick={() => useSuggestion(s)}>{s}</button>
					{/each}
				</div>
			</div>
		{:else if suggestionsHidden}
			<button class="suggestions-show" onclick={() => setSuggestionsHidden(false)}>
				Show suggestions
			</button>
		{/if}
	{/if}

	<div class="options-row">
		<div class="option-group">
			<span class="option-label">Mode</span>
			<div class="mode-grid">
				{#each modeList as [key, info]}
					<button
						class="mode-btn"
						class:active={selectedMode === key}
						onclick={() => (selectedMode = key)}
						disabled={isRunning}
					>
						{key}
					</button>
				{/each}
			</div>
		</div>
		<div class="option-group">
			<span class="option-label">Rounds</span>
			<div class="segmented-control">
				{#each [1, 2, 3, 4, 5] as n}
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
		<div class="option-group">
			<span class="option-label">Model</span>
			<div class="segmented-control">
				{#each MODEL_OPTIONS as m}
					<button
						class="seg-btn"
						class:active={selectedModel === m.key}
						onclick={() => (selectedModel = m.key)}
						disabled={isRunning}
						title={m.hint}
					>
						{m.label}
					</button>
				{/each}
			</div>
		</div>
	</div>

	{#if currentModeInfo && !hasDebate && !isRunning}
		<div class="mode-detail">
			<p class="mode-description">{currentModeInfo.description}</p>
			<div class="agents-preview">
				{#each Object.entries(currentModeInfo.agents) as [name, agent]}
					<span class="agent-tag" style="--agent-color: {agentColor(agent.color)}">
						{name}
					</span>
				{/each}
			</div>
		</div>
	{/if}
</div>

<style>
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
	.controls {
		display: flex;
		flex-direction: column;
		gap: 12px;
	}
	.controls.compact { gap: 10px; }
	.input-row {
		display: flex;
		gap: 8px;
		align-items: flex-start;
	}
	.kbd-hint {
		font-size: 11px;
		color: var(--text-muted);
		display: flex;
		align-items: center;
		gap: 4px;
		flex-wrap: wrap;
	}
	.kbd-hint kbd {
		font-family: var(--font-mono);
		font-size: 10px;
		padding: 1px 5px;
		background: var(--bg-surface);
		border: 1px solid var(--border);
		border-radius: 4px;
		color: var(--text-dim);
	}
	.repo-row {
		display: flex;
		align-items: center;
		gap: 8px;
		padding: 7px 12px;
		background: var(--bg-surface);
		border: 1px solid var(--border);
		border-radius: var(--radius-sm);
		transition: border-color 0.2s, box-shadow 0.2s;
	}
	.repo-row:focus-within {
		border-color: var(--accent);
		box-shadow: 0 0 0 2px var(--accent-glow);
	}
	.repo-icon {
		color: var(--text-muted);
		flex-shrink: 0;
	}
	.repo-input {
		flex: 1;
		background: transparent;
		border: none;
		outline: none;
		color: var(--text);
		font-size: 13px;
		font-family: var(--font-mono);
	}
	.repo-input::placeholder {
		color: var(--text-muted);
		font-family: var(--font-sans);
	}
	.repo-input:disabled { opacity: 0.5; }
	.repo-clear {
		background: none;
		border: none;
		color: var(--text-muted);
		cursor: pointer;
		font-size: 12px;
		padding: 2px 4px;
		flex-shrink: 0;
	}
	.repo-clear:hover { color: var(--text); }
	.question-input {
		flex: 1;
		padding: 11px 16px;
		background: var(--bg-surface);
		border: 1px solid var(--border);
		border-radius: var(--radius-sm);
		color: var(--text);
		font-size: 14px;
		line-height: 1.5;
		font-family: var(--font-sans);
		outline: none;
		transition: border-color 0.2s, box-shadow 0.2s;
		resize: none;
		overflow-y: auto;
		max-height: 220px;
		min-height: 44px;
	}
	.question-input:focus {
		border-color: var(--accent);
		box-shadow: 0 0 0 2px var(--accent-glow);
	}
	.question-input::placeholder { color: var(--text-muted); }
	.question-input:disabled { opacity: 0.5; }
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
	.launch-btn:hover:not(:disabled) { filter: brightness(1.1); }
	.launch-btn:disabled { opacity: 0.35; cursor: not-allowed; }
	.new-btn {
		padding: 11px 18px;
		background: var(--bg-elevated);
		color: var(--text-dim);
		border: 1px solid var(--border);
		border-radius: var(--radius-sm);
		font-size: 14px;
		font-weight: 500;
		font-family: var(--font-sans);
		cursor: pointer;
		transition: all 0.15s;
		white-space: nowrap;
	}
	.new-btn:hover {
		color: var(--text);
		border-color: var(--border-accent);
	}
	.improve-btn {
		display: flex;
		align-items: center;
		gap: 6px;
		padding: 11px 18px;
		background: var(--bg-elevated);
		color: var(--text-dim);
		border: 1px solid var(--border);
		border-radius: var(--radius-sm);
		font-size: 14px;
		font-weight: 500;
		font-family: var(--font-sans);
		cursor: pointer;
		transition: all 0.15s;
		white-space: nowrap;
	}
	.improve-btn:hover:not(:disabled) {
		color: var(--accent);
		border-color: var(--border-accent);
	}
	.improve-btn:disabled { opacity: 0.5; cursor: not-allowed; }
	.spinner {
		width: 12px;
		height: 12px;
		border: 2px solid currentColor;
		border-top-color: transparent;
		border-radius: 50%;
		animation: spin 0.7s linear infinite;
	}
	@keyframes spin {
		to { transform: rotate(360deg); }
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
	.stop-btn:hover { background: var(--red); color: white; }
	.suggestions {
		display: flex;
		flex-direction: column;
		gap: 8px;
	}
	.suggestions-head {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 8px;
	}
	.suggestions-label {
		font-size: 11px;
		font-weight: 600;
		color: var(--text-muted);
		text-transform: uppercase;
		letter-spacing: 0.06em;
	}
	.suggestions-shuffle {
		display: inline-flex;
		align-items: center;
		gap: 5px;
		padding: 4px 10px;
		background: transparent;
		border: 1px solid var(--border);
		border-radius: 6px;
		color: var(--text-muted);
		font-size: 11px;
		font-weight: 500;
		font-family: var(--font-mono);
		cursor: pointer;
		transition: all 0.15s;
	}
	.suggestions-shuffle:hover {
		color: var(--accent);
		border-color: var(--border-accent);
	}
	.suggestions-actions {
		display: flex;
		align-items: center;
		gap: 6px;
	}
	.suggestions-hide {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		padding: 4px;
		background: transparent;
		border: 1px solid var(--border);
		border-radius: 6px;
		color: var(--text-muted);
		cursor: pointer;
		transition: all 0.15s;
	}
	.suggestions-hide:hover {
		color: var(--text);
		border-color: var(--border-accent);
	}
	.suggestions-show {
		align-self: flex-start;
		padding: 4px 0;
		background: transparent;
		border: none;
		color: var(--text-muted);
		font-size: 12px;
		font-family: var(--font-sans);
		cursor: pointer;
		transition: color 0.15s;
	}
	.suggestions-show:hover {
		color: var(--accent);
		text-decoration: underline;
	}
	.suggestion-list {
		display: flex;
		flex-wrap: wrap;
		gap: 6px;
	}
	.suggestion-item {
		text-align: left;
		padding: 8px 12px;
		background: var(--bg-surface);
		border: 1px solid var(--border);
		border-radius: var(--radius-sm);
		color: var(--text-dim);
		font-size: 13px;
		font-family: var(--font-sans);
		line-height: 1.4;
		cursor: pointer;
		transition: all 0.15s;
	}
	.suggestion-item:hover {
		color: var(--text);
		background: var(--bg-hover);
		border-color: var(--border-accent);
	}
	.options-row {
		display: flex;
		gap: 20px;
		align-items: flex-start;
		flex-wrap: wrap;
	}
	.option-group {
		display: flex;
		align-items: flex-start;
		gap: 8px;
	}
	.option-label {
		font-size: 11px;
		font-weight: 600;
		color: var(--text-muted);
		text-transform: uppercase;
		letter-spacing: 0.06em;
		padding-top: 6px;
	}

	/* Mode grid — wraps naturally with 6 modes */
	.mode-grid {
		display: flex;
		flex-wrap: wrap;
		gap: 4px;
	}
	.mode-btn {
		padding: 5px 12px;
		background: var(--bg-surface);
		border: 1px solid var(--border);
		border-radius: 6px;
		color: var(--text-dim);
		font-size: 12px;
		font-weight: 500;
		font-family: var(--font-sans);
		cursor: pointer;
		transition: all 0.15s;
		text-transform: capitalize;
	}
	.mode-btn:hover:not(:disabled):not(.active) {
		background: var(--bg-hover);
		color: var(--text);
		border-color: var(--border-accent);
	}
	.mode-btn.active {
		background: var(--accent);
		border-color: var(--accent);
		color: white;
	}
	.mode-btn:disabled { opacity: 0.4; cursor: not-allowed; }

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
	.seg-btn:last-child { border-right: none; }
	.seg-btn:hover:not(:disabled):not(.active) {
		background: var(--bg-hover);
		color: var(--text);
	}
	.seg-btn.active { background: var(--accent); color: white; }
	.seg-btn:disabled { opacity: 0.4; cursor: not-allowed; }

	/* Mode detail: description + agents */
	.mode-detail {
		display: flex;
		flex-direction: column;
		gap: 8px;
	}
	.mode-description {
		font-size: 12px;
		color: var(--text-dim);
		line-height: 1.5;
	}
	.agents-preview {
		display: flex;
		gap: 6px;
		flex-wrap: wrap;
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

	@media (max-width: 768px) {
		.options-row {
			flex-direction: column;
			align-items: flex-start;
			gap: 10px;
		}
		.input-row { flex-direction: column; }
	}
</style>
