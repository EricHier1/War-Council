<script lang="ts">
	import { renderMarkdown } from '$lib/markdown';
	import CopyButton from './CopyButton.svelte';
	import type { StructuredVerdict } from '$lib/types';
	import '$lib/styles/prose.css';

	let {
		verdict,
		structured = null,
		title = 'Verdict',
	}: {
		verdict: string;
		structured?: StructuredVerdict | null;
		title?: string;
	} = $props();

	// Fields rendered as colored badges in the meta row.
	const BADGE_KEYS = ['recommendation', 'risk_posture', 'confidence'];
	// Preferred order for the remaining (body) fields.
	const PRIORITY = [
		'decision', 'correct_answer', 'winning_idea', 'verdict', 'most_dangerous_flaw',
		'strongest_argument', 'strongest_reason', 'core_tension', 'unresolved_tension',
		'vulnerabilities', 'incorrect_claims', 'next_steps', 'must_be_true',
		'prioritized_fixes', 'ninety_day_milestones', 'caveats', 'biggest_risk',
		'biggest_open_risk', 'strongest_dissent', 'additional_context',
	];

	function humanize(k: string): string {
		if (k === 'tldr') return 'TL;DR';
		return k
			.replace('ninety_day', '90_day')
			.split('_')
			.map((w) => w.charAt(0).toUpperCase() + w.slice(1))
			.join(' ');
	}

	function badgeKind(val: string): string {
		const v = String(val).toLowerCase();
		if (['high', 'go', 'green'].includes(v)) return 'good';
		if (['medium', 'conditional_go', 'yellow'].includes(v)) return 'warn';
		if (['low', 'no_go', 'red', 'critical'].includes(v)) return 'bad';
		return '';
	}

	function isFilled(v: unknown): boolean {
		return v != null && v !== '' && !(Array.isArray(v) && v.length === 0);
	}

	let s = $derived(structured ?? {});
	let tldr = $derived(typeof s.tldr === 'string' ? s.tldr : '');
	let badges = $derived([
		...BADGE_KEYS.filter((k) => isFilled(s[k])).map((k) => ({ key: k, val: String(s[k]) })),
		...(isFilled(s.winning_agent) ? [{ key: 'winning_agent', val: String(s.winning_agent) }] : []),
	]);
	let body = $derived(
		Object.entries(s)
			.filter(([k, v]) => k !== 'tldr' && !BADGE_KEYS.includes(k) && k !== 'winning_agent' && isFilled(v))
			.sort((a, b) => {
				const ia = PRIORITY.indexOf(a[0]);
				const ib = PRIORITY.indexOf(b[0]);
				return (ia < 0 ? 999 : ia) - (ib < 0 ? 999 : ib);
			})
	);

	const isObjArray = (v: unknown): v is Record<string, any>[] =>
		Array.isArray(v) && v.length > 0 && typeof v[0] === 'object' && v[0] !== null;
</script>

<div class="verdict-block">
	<div class="verdict-header-row">
		<div class="verdict-header">{title}</div>
		<CopyButton text={verdict} label="Copy verdict" />
	</div>

	{#if structured}
		<div class="verdict-card">
			{#if tldr}<p class="v-tldr">{tldr}</p>{/if}

			{#if badges.length}
				<div class="v-meta">
					{#each badges as b}
						<span class="v-badge {b.key === 'winning_agent' ? '' : `kind-${badgeKind(b.val)}`}">
							{#if b.key === 'winning_agent'}Strongest case: {b.val}
							{:else if b.key === 'confidence'}{b.val} confidence
							{:else}{b.val.replaceAll('_', ' ')}{/if}
						</span>
					{/each}
				</div>
			{/if}

			{#each body as [key, val]}
				<div class="v-section">
					<span class="v-label">{humanize(key)}</span>
					{#if typeof val === 'string'}
						<p class="v-text">{val}</p>
					{:else if isObjArray(val)}
						<div class="v-items">
							{#each val as item}
								<div class="v-item">
									{#if item.title || item.claim}
										<div class="v-item-head">
											<span class="v-item-title">{item.title ?? item.claim}</span>
											{#if item.severity}
												<span class="v-badge kind-{badgeKind(item.severity)}">{item.severity}</span>
											{/if}
										</div>
									{/if}
									{#each Object.entries(item) as [ik, iv]}
										{#if !['title', 'claim', 'severity'].includes(ik) && iv}
											<p class="v-item-detail"><span class="v-item-key">{humanize(ik)}:</span> {iv}</p>
										{/if}
									{/each}
								</div>
							{/each}
						</div>
					{:else if Array.isArray(val)}
						<ul class="v-reasons">
							{#each val as r}<li>{r}</li>{/each}
						</ul>
					{/if}
				</div>
			{/each}
		</div>
	{:else}
		<div class="verdict-text prose">{@html renderMarkdown(verdict)}</div>
	{/if}
</div>

<style>
	.verdict-block {
		background: var(--bg-elevated);
		border: 1px solid var(--accent);
		border-left: 4px solid var(--accent);
		border-radius: 6px;
		padding: 20px 24px;
	}
	.verdict-header-row {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 8px;
		margin-bottom: 12px;
	}
	.verdict-header {
		font-size: 11px;
		font-weight: 700;
		text-transform: uppercase;
		letter-spacing: 0.1em;
		color: var(--accent);
		font-family: var(--font-mono);
	}
	.verdict-text {
		font-size: 14px;
		line-height: 1.7;
		color: var(--text);
	}

	.verdict-card {
		display: flex;
		flex-direction: column;
		gap: 14px;
	}
	.v-tldr {
		font-size: 15px;
		font-weight: 600;
		line-height: 1.5;
		color: var(--text);
	}
	.v-section {
		display: flex;
		flex-direction: column;
		gap: 4px;
	}
	.v-label {
		font-size: 10px;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.06em;
		color: var(--text-muted);
		font-family: var(--font-mono);
	}
	.v-text {
		font-size: 14px;
		line-height: 1.6;
		color: var(--text);
	}
	.v-meta {
		display: flex;
		flex-wrap: wrap;
		gap: 6px;
	}
	.v-badge {
		font-size: 11px;
		font-weight: 500;
		font-family: var(--font-mono);
		padding: 3px 9px;
		border-radius: 4px;
		color: var(--text-dim);
		background: var(--bg-surface);
		border: 1px solid var(--border);
		text-transform: capitalize;
	}
	.v-badge.kind-good { color: var(--green, #3fb950); border-color: color-mix(in srgb, var(--green, #3fb950) 35%, transparent); }
	.v-badge.kind-warn { color: var(--yellow, #d29922); border-color: color-mix(in srgb, var(--yellow, #d29922) 35%, transparent); }
	.v-badge.kind-bad { color: var(--red, #f85149); border-color: color-mix(in srgb, var(--red, #f85149) 35%, transparent); }
	.v-reasons {
		margin: 0;
		padding-left: 18px;
		display: flex;
		flex-direction: column;
		gap: 5px;
	}
	.v-reasons li {
		font-size: 13.5px;
		line-height: 1.55;
		color: var(--text);
	}
	.v-items {
		display: flex;
		flex-direction: column;
		gap: 8px;
	}
	.v-item {
		background: var(--bg-surface);
		border: 1px solid var(--border);
		border-radius: 6px;
		padding: 10px 12px;
		display: flex;
		flex-direction: column;
		gap: 4px;
	}
	.v-item-head {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 8px;
	}
	.v-item-title {
		font-size: 13.5px;
		font-weight: 600;
		color: var(--text);
	}
	.v-item-detail {
		font-size: 13px;
		line-height: 1.5;
		color: var(--text-dim);
	}
	.v-item-key {
		font-weight: 600;
		color: var(--text);
	}
</style>
