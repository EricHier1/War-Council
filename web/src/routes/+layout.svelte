<script lang="ts">
	import '../app.css';
	let { children } = $props();
</script>

<svelte:head>
	<title>Agent Colosseum</title>
</svelte:head>

{@render children()}
