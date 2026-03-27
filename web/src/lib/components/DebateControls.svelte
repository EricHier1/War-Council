<script lang="ts">
	import { agentColor } from '$lib/colors';
	import type { Modes } from '$lib/types';

	let {
		question = $bindable(),
		selectedMode = $bindable(),
		selectedRounds = $bindable(),
		unlimited = $bindable(),
		modes,
		isRunning,
		hasDebate,
		onLaunch,
		onStop,
	}: {
		question: string;
		selectedMode: string;
		selectedRounds: number;
		unlimited: boolean;
		modes: Modes;
		isRunning: boolean;
		hasDebate: boolean;
		onLaunch: () => void;
		onStop: () => void;
	} = $props();

	let modeList = $derived(Object.entries(modes));
	let currentModeInfo = $derived(modes[selectedMode]);
</script>

{#if !hasDebate && !isRunning}
	<div class="header">
		<h1 class="logo">Agent Colosseum</h1>
		<p class="tagline">Multi-agent debate arena powered by Claude</p>
	</div>
{/if}

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
			<button class="stop-btn" onclick={onStop}>
				<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><rect x="4" y="4" width="16" height="16" rx="2"/></svg>
				Stop
			</button>
		{:else}
			<button class="launch-btn" onclick={onLaunch} disabled={!question.trim()}>
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
	.seg-btn:last-child { border-right: none; }
	.seg-btn:hover:not(:disabled):not(.active) {
		background: var(--bg-hover);
		color: var(--text);
	}
	.seg-btn.active { background: var(--accent); color: white; }
	.seg-btn:disabled { opacity: 0.4; cursor: not-allowed; }
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

	@media (max-width: 768px) {
		.options-row {
			flex-direction: column;
			align-items: flex-start;
			gap: 10px;
		}
		.agents-preview { margin-left: 0; }
		.input-row { flex-direction: column; }
	}
</style>
