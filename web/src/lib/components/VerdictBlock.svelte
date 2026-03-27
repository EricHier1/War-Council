<script lang="ts">
	import { renderMarkdown } from '$lib/markdown';
	import '$lib/styles/prose.css';

	let {
		verdict,
		title = 'Verdict',
	}: {
		verdict: string;
		title?: string;
	} = $props();
</script>

<div class="verdict-block">
	<div class="verdict-header">{title}</div>
	<div class="verdict-text prose">{@html renderMarkdown(verdict)}</div>
</div>

<style>
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
</style>
