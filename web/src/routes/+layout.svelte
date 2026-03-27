<script lang="ts">
	import { onMount } from 'svelte';
	import '../app.css';
	import { getInitialTheme, applyTheme } from '$lib/theme';

	let { children } = $props();

	onMount(() => {
		applyTheme(getInitialTheme());
	});
</script>

<svelte:head>
	<title>Agent Colosseum</title>
</svelte:head>

{@render children()}
