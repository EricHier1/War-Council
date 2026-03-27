<script lang="ts">
	let {
		value = $bindable(),
		disabled = false,
		onSend,
	}: {
		value: string;
		disabled: boolean;
		onSend: () => void;
	} = $props();
</script>

<div class="followup-row">
	<input
		class="followup-input"
		type="text"
		placeholder="Ask a follow-up question..."
		bind:value
	/>
	<button class="btn-secondary" onclick={onSend} {disabled}>
		Send
	</button>
</div>

<style>
	.followup-row {
		display: flex;
		gap: 8px;
		padding-top: 4px;
		flex-shrink: 0;
	}
	.followup-input {
		flex: 1;
		padding: 10px 14px;
		background: var(--bg-surface);
		border: 1px solid var(--border);
		border-radius: 6px;
		color: var(--text);
		font-size: 13px;
		font-family: var(--font-sans);
		outline: none;
		transition: border-color 0.2s, box-shadow 0.2s;
	}
	.followup-input:focus {
		border-color: var(--accent);
		box-shadow: 0 0 0 2px var(--accent-glow);
	}
	.followup-input::placeholder { color: var(--text-muted); }
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
	.btn-secondary:disabled {
		opacity: 0.35;
		cursor: not-allowed;
	}
</style>
