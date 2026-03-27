/**
 * Map Rich/terminal color names to CSS colors.
 */
const COLOR_MAP: Record<string, string> = {
	red: 'var(--red)',
	yellow: 'var(--yellow)',
	green: 'var(--green)',
	blue: 'var(--blue)',
	magenta: 'var(--magenta)',
	bright_cyan: 'var(--cyan)',
	cyan: 'var(--cyan)',
	white: 'var(--text)',
	orange: 'var(--orange)',
};

export function agentColor(richColor: string): string {
	return COLOR_MAP[richColor] || 'var(--text)';
}
