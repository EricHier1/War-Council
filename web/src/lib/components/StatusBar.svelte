<script lang="ts">
	let {
		spinner,
		completedRounds,
		visible,
	}: {
		spinner: string;
		completedRounds: number;
		visible: boolean;
	} = $props();
</script>

{#if visible}
	<div class="status-bar">
		<div class="pulse"></div>
		<span>{spinner}</span>
		{#if completedRounds > 0}
			<span class="status-meta">
				{completedRounds} round{completedRounds !== 1 ? 's' : ''} complete
			</span>
		{/if}
	</div>
{/if}

<style>
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
</style>
