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
}

export type DebateStatus = 'idle' | 'running' | 'judging' | 'done' | 'error';
