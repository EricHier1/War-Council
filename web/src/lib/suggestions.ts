// Seed questions surfaced as clickable suggestions under the prompt box,
// grouped by theme so a balanced mix can be shown.
export const SUGGESTION_CATEGORIES: Record<string, string[]> = {
	philosophy: [
		'Is free will an illusion, or are we genuinely the authors of our choices?',
		'Is a meaningful life better than a merely happy one?',
		'Does objective morality exist, or is all ethics ultimately subjective?',
		'Is the self a continuous entity or a convenient illusion?',
		'Would you enter a machine that gave you perfect, simulated happiness forever?',
		'Does the meaning of life come from within us or from something beyond us?'
	],
	stoicism: [
		'Is it truly possible to be indifferent to everything outside our control?',
		'Is virtue sufficient for a good life, or do we also need external goods?',
		'Does focusing only on what you control lead to inner peace or to passivity?',
		'Is the Stoic acceptance of fate compatible with striving to change the world?',
		'Should we aim to master our emotions or to be free of them entirely?',
		'Is enduring hardship without complaint a strength or a form of self-denial?'
	],
	tech: [
		'Should artificial general intelligence development be paused until safety is solved?',
		'Will open-source AI models do more good than harm?',
		'Is privacy more important than security in the digital age?',
		'Should companies be legally required to disclose when content is AI-generated?',
		'Does social media make us more connected or more isolated?',
		'Will AI augment human intelligence or gradually erode it?'
	],
	fitness: [
		'Is strength training more important than cardio for long-term health?',
		'For fat loss, is a calorie deficit all that matters, or does food quality matter more?',
		'Do you need to train to failure to maximize muscle growth?',
		'Are free weights genuinely superior to machines for building muscle?',
		'Is fasting an effective health tool, or just calorie restriction in disguise?',
		'Is consistency more important than intensity for long-term progress?'
	]
};

/** Flat list of every suggested question across all categories. */
export const SUGGESTED_QUESTIONS: string[] = Object.values(SUGGESTION_CATEGORIES).flat();

function shuffle<T>(arr: T[]): T[] {
	const out = [...arr];
	for (let i = out.length - 1; i > 0; i--) {
		const j = Math.floor(Math.random() * (i + 1));
		[out[i], out[j]] = [out[j], out[i]];
	}
	return out;
}

/**
 * Return `n` distinct suggestions with a balanced spread: one random question
 * from each category (in random order), topping up from the full pool if more
 * are requested than there are categories.
 */
export function pickSuggestions(n: number): string[] {
	const picked: string[] = [];
	for (const list of shuffle(Object.values(SUGGESTION_CATEGORIES))) {
		if (picked.length >= n) break;
		picked.push(list[Math.floor(Math.random() * list.length)]);
	}
	while (picked.length < n && picked.length < SUGGESTED_QUESTIONS.length) {
		const q = SUGGESTED_QUESTIONS[Math.floor(Math.random() * SUGGESTED_QUESTIONS.length)];
		if (!picked.includes(q)) picked.push(q);
	}
	return shuffle(picked).slice(0, n);
}
