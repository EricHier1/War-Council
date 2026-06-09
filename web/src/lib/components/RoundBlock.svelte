<script lang="ts">
	import { agentColor } from '$lib/colors';
	import { renderMarkdown } from '$lib/markdown';
	import type { RoundData } from '$lib/types';
	import CopyButton from './CopyButton.svelte';
	import '$lib/styles/prose.css';

	let {
		round = undefined,
		followup = undefined,
		agentColors,
		isFollowup = false,
	}: {
		round?: RoundData;
		followup?: { question: string; responses: Record<string, string>; models?: Record<string, string> };
		agentColors: Record<string, string>;
		isFollowup?: boolean;
	} = $props();

	let label = $derived(isFollowup ? 'Follow-up' : `Round ${round?.round}`);
	let title = $derived(isFollowup ? followup?.question : round?.title);
	let responses = $derived(isFollowup ? followup?.responses ?? {} : round?.responses ?? {});
	let models = $derived(isFollowup ? followup?.models ?? {} : round?.models ?? {});
	let hasResponses = $derived(Object.keys(responses).length > 0);
</script>

<div class="round-block">
	<div class="round-header">
		<div class="round-label">
			<span class="round-num">{label}</span>
			<span class="round-divider">/</span>
			<span class="round-title">{title}</span>
		</div>
	</div>
	{#if hasResponses}
		<div class="responses">
			{#each Object.entries(responses) as [agent, response]}
				<div class="response" style="--agent-color: {agentColor(agentColors[agent] || 'white')}">
					<div class="response-head">
						<div class="agent-name">
							{agent}
							{#if models[agent]}<span class="agent-model">{models[agent]}</span>{/if}
						</div>
						<CopyButton text={response} label={`Copy ${agent}`} />
					</div>
					<div class="agent-response prose">{@html renderMarkdown(response)}</div>
				</div>
			{/each}
		</div>
	{/if}
</div>

<style>
	.round-block {
		display: flex;
		flex-direction: column;
		gap: 10px;
	}
	.round-header { padding: 4px 0; }
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
	.response-head {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 8px;
		margin-bottom: 6px;
	}
	.agent-name {
		font-size: 12px;
		font-weight: 600;
		font-family: var(--font-mono);
		color: var(--agent-color, var(--text));
		text-transform: uppercase;
		letter-spacing: 0.04em;
		display: flex;
		align-items: center;
		gap: 6px;
	}
	.agent-model {
		font-size: 9px;
		font-weight: 500;
		text-transform: none;
		letter-spacing: 0;
		color: var(--text-muted);
		background: color-mix(in srgb, var(--agent-color, var(--border)) 12%, transparent);
		border: 1px solid color-mix(in srgb, var(--agent-color, var(--border)) 25%, transparent);
		border-radius: 3px;
		padding: 0 5px;
	}
	.agent-response {
		font-size: 14px;
		line-height: 1.65;
		color: var(--text);
	}
</style>
