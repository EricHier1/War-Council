<script lang="ts">
	import { agentColor } from '$lib/colors';
	import { renderMarkdown } from '$lib/markdown';
	import type { RoundData } from '$lib/types';
	import '$lib/styles/prose.css';

	let {
		round = undefined,
		followup = undefined,
		agentColors,
		isFollowup = false,
	}: {
		round?: RoundData;
		followup?: { question: string; responses: Record<string, string> };
		agentColors: Record<string, string>;
		isFollowup?: boolean;
	} = $props();

	let label = $derived(isFollowup ? 'Follow-up' : `Round ${round?.round}`);
	let title = $derived(isFollowup ? followup?.question : round?.title);
	let responses = $derived(isFollowup ? followup?.responses ?? {} : round?.responses ?? {});
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
					<div class="agent-name">{agent}</div>
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
</style>
