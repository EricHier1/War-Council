export interface AgentColors {
	[name: string]: string;
}

export interface ModeInfo {
	name: string;
	description: string;
	agents: { [name: string]: { color: string } };
}

export interface Modes {
	[key: string]: ModeInfo;
}

export interface TranscriptEntry {
	filename: string;
	stem: string;
	size: number;
	modified: string;
}

export interface RoundData {
	round: number;
	title: string;
	responses: { [agent: string]: string };
	models?: { [agent: string]: string };
}

export type DebateStatus = 'idle' | 'running' | 'judging' | 'done' | 'error';

export interface Metrics {
	cost_usd: number;
	input_tokens: number;
	output_tokens: number;
	elapsed_ms: number;
}

// Mode-specific schemas vary the shape, so the verdict is a generic record
// rendered by VerdictBlock (strings, string arrays, and object arrays).
export type StructuredVerdict = Record<string, any>;
