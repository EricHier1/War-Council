<script lang="ts">
	import { renderMarkdown } from '$lib/markdown';
	import '$lib/styles/prose.css';

	let {
		transcript,
		onClose,
		onRerun,
	}: {
		transcript: { filename: string; content: string; question?: string; mode?: string | null };
		onClose: () => void;
		onRerun?: (question: string, mode: string | null) => void;
	} = $props();
</script>

<div class="transcript-viewer">
	<div class="transcript-viewer-header">
		<h2>{transcript.filename}</h2>
		<div class="transcript-actions">
			{#if onRerun && transcript.question}
				<button
					class="btn-secondary btn-sm"
					onclick={() => onRerun?.(transcript.question!, transcript.mode ?? null)}
					title="Run this question again as a new debate"
				>
					Re-run
				</button>
			{/if}
			<button class="btn-secondary btn-sm" onclick={onClose}>Close</button>
		</div>
	</div>
	<div class="transcript-content prose">
		{@html renderMarkdown(transcript.content)}
	</div>
</div>

<style>
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
		flex-shrink: 0;
	}
	.transcript-actions {
		display: flex;
		gap: 8px;
		flex-shrink: 0;
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
		font-size: 14px;
		line-height: 1.7;
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
	.btn-sm {
		padding: 6px 14px;
		font-size: 12px;
	}
</style>
