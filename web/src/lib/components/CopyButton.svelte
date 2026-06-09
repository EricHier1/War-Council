<script lang="ts">
	import { onDestroy } from 'svelte';

	let { text, label = 'Copy' }: { text: string; label?: string } = $props();

	let copied = $state(false);
	let timer: ReturnType<typeof setTimeout> | undefined;

	async function copy() {
		try {
			await navigator.clipboard.writeText(text);
			copied = true;
			clearTimeout(timer);
			timer = setTimeout(() => (copied = false), 1500);
		} catch {
			copied = false;
		}
	}

	onDestroy(() => clearTimeout(timer));
</script>

<button
	class="copy-btn"
	class:copied
	onclick={copy}
	title={copied ? 'Copied' : 'Copy to clipboard'}
	aria-label={copied ? 'Copied to clipboard' : label}
>
	{#if copied}
		<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" aria-hidden="true"><path d="M20 6 9 17l-5-5"/></svg>
		Copied
	{:else}
		<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
		{label}
	{/if}
</button>

<style>
	.copy-btn {
		display: inline-flex;
		align-items: center;
		gap: 4px;
		padding: 3px 8px;
		background: transparent;
		border: 1px solid var(--border);
		border-radius: 5px;
		color: var(--text-muted);
		font-size: 11px;
		font-weight: 500;
		font-family: var(--font-mono);
		cursor: pointer;
		transition: all 0.15s;
		opacity: 0.7;
	}
	.copy-btn:hover {
		opacity: 1;
		color: var(--text);
		border-color: var(--border-accent);
	}
	.copy-btn.copied {
		opacity: 1;
		color: var(--green, #3fb950);
		border-color: color-mix(in srgb, var(--green, #3fb950) 40%, transparent);
	}
</style>
