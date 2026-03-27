<script lang="ts">
	let {
		transcript,
		onClose,
	}: {
		transcript: { filename: string; content: string };
		onClose: () => void;
	} = $props();
</script>

<div class="transcript-viewer">
	<div class="transcript-viewer-header">
		<h2>{transcript.filename}</h2>
		<button class="btn-secondary btn-sm" onclick={onClose}>Close</button>
	</div>
	<div class="transcript-content">
		<pre>{transcript.content}</pre>
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
