<script lang="ts">
	import { onMount } from 'svelte';
	import { getInitialTheme, applyTheme, toggleTheme, type Theme } from '$lib/theme';

	let theme: Theme = $state('dark');

	onMount(() => {
		theme = getInitialTheme();
	});

	function toggle() {
		theme = toggleTheme(theme);
		applyTheme(theme);
	}
</script>

<button class="theme-toggle" onclick={toggle} title="Toggle theme">
	{#if theme === 'dark'}
		<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>
	{:else}
		<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>
	{/if}
</button>

<style>
	.theme-toggle {
		position: absolute;
		top: 16px;
		right: 16px;
		background: var(--bg-surface);
		border: 1px solid var(--border);
		border-radius: 6px;
		color: var(--text-dim);
		cursor: pointer;
		padding: 6px;
		display: flex;
		align-items: center;
		justify-content: center;
		transition: all 0.15s;
		z-index: 10;
	}
	.theme-toggle:hover {
		color: var(--text);
		border-color: var(--border-accent);
	}
</style>
