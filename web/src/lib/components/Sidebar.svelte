<script lang="ts">
	import type { TranscriptEntry } from '$lib/types';

	let {
		transcripts,
		open,
		onToggle,
		onRefresh,
		onSelect,
	}: {
		transcripts: TranscriptEntry[];
		open: boolean;
		onToggle: () => void;
		onRefresh: () => void;
		onSelect: (filename: string) => void;
	} = $props();
</script>

<button class="sidebar-toggle" onclick={onToggle}>
	{open ? '\u2715' : '\u2630'}
</button>

<aside class="sidebar" class:open>
	<div class="sidebar-header">
		<h2>History</h2>
		<button class="icon-btn" onclick={onRefresh} title="Refresh">
			<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 2v6h-6"/><path d="M3 12a9 9 0 0 1 15-6.7L21 8"/><path d="M3 22v-6h6"/><path d="M21 12a9 9 0 0 1-15 6.7L3 16"/></svg>
		</button>
	</div>
	<div class="transcript-list">
		{#each transcripts as t}
			<button class="transcript-item" onclick={() => onSelect(t.filename)}>
				<span class="transcript-name">{t.stem.split('_').slice(1).join(' ').replaceAll('-', ' ')}</span>
				<span class="transcript-date">{t.stem.split('_')[0]}</span>
			</button>
		{:else}
			<p class="empty-msg">No sessions yet</p>
		{/each}
	</div>
</aside>

<style>
	.sidebar {
		width: 260px;
		min-width: 260px;
		background: var(--bg-surface);
		border-right: 1px solid var(--border);
		display: flex;
		flex-direction: column;
		overflow: hidden;
	}
	.sidebar-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 16px 16px 12px;
		border-bottom: 1px solid var(--border);
	}
	.sidebar-header h2 {
		font-size: 11px;
		font-weight: 600;
		color: var(--text-muted);
		text-transform: uppercase;
		letter-spacing: 0.08em;
	}
	.icon-btn {
		background: none;
		border: none;
		color: var(--text-muted);
		cursor: pointer;
		padding: 4px;
		border-radius: 4px;
		display: flex;
		align-items: center;
		transition: color 0.15s;
	}
	.icon-btn:hover { color: var(--text); }
	.transcript-list {
		flex: 1;
		overflow-y: auto;
		padding: 6px;
	}
	.transcript-item {
		display: flex;
		flex-direction: column;
		gap: 2px;
		width: 100%;
		padding: 8px 10px;
		background: none;
		border: none;
		border-radius: 6px;
		color: var(--text);
		cursor: pointer;
		text-align: left;
		transition: background 0.15s;
	}
	.transcript-item:hover { background: var(--bg-hover); }
	.transcript-name {
		font-size: 13px;
		font-weight: 500;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
		line-height: 1.4;
	}
	.transcript-date {
		font-size: 11px;
		color: var(--text-muted);
		font-family: var(--font-mono);
	}
	.empty-msg {
		padding: 24px 16px;
		text-align: center;
		color: var(--text-muted);
		font-size: 13px;
	}
	.sidebar-toggle { display: none; }

	@media (max-width: 768px) {
		.sidebar {
			position: fixed;
			left: 0;
			top: 0;
			bottom: 0;
			z-index: 100;
			transform: translateX(-100%);
			transition: transform 0.2s ease;
			box-shadow: 4px 0 24px #00000066;
		}
		.sidebar.open { transform: translateX(0); }
		.sidebar-toggle {
			display: flex;
			align-items: center;
			justify-content: center;
			position: fixed;
			top: 12px;
			left: 12px;
			z-index: 101;
			width: 36px;
			height: 36px;
			background: var(--bg-elevated);
			border: 1px solid var(--border);
			border-radius: 6px;
			color: var(--text);
			font-size: 18px;
			cursor: pointer;
		}
	}
</style>
