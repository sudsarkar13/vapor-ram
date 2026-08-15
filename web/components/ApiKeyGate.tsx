"use client";

import React, { useState, useEffect, useCallback } from "react";
import { KeyRound, Loader2, ShieldAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { onUnauthorized, setApiKey, verifyApiKey } from "@/lib/api";

/**
 * Blocking prompt shown when the engine answers 401.
 *
 * A shared server normally sends people a link with ?key= already in it, which
 * api.ts consumes silently — this gate is the fallback for someone who typed
 * the bare host, or whose stored key was rotated out from under them.
 */
export function ApiKeyGate() {
	const [open, setOpen] = useState(false);
	const [value, setValue] = useState("");
	const [checking, setChecking] = useState(false);
	const [error, setError] = useState<string | null>(null);

	useEffect(() => onUnauthorized(() => setOpen(true)), []);

	const submit = useCallback(async () => {
		const candidate = value.trim();
		if (!candidate) return;
		setChecking(true);
		setError(null);
		// Verified before it is stored, so a typo surfaces here instead of
		// turning every subsequent poll into a silent failure.
		const ok = await verifyApiKey(candidate);
		setChecking(false);
		if (!ok) {
			setError("That key was rejected by the server.");
			return;
		}
		setApiKey(candidate);
		setOpen(false);
		setValue("");
	}, [value]);

	if (!open) return null;

	return (
		<div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/90 backdrop-blur-sm p-4">
			<div className="w-full max-w-md rounded-xl border border-cyan-500/30 bg-slate-900 p-6 shadow-2xl">
				<div className="flex items-center gap-3 mb-3">
					<div className="rounded-lg bg-cyan-950/60 border border-cyan-500/30 p-2">
						<ShieldAlert className="h-5 w-5 text-cyan-400" />
					</div>
					<div>
						<h2 className="text-base font-semibold text-slate-100">
							API key required
						</h2>
						<p className="text-xs text-slate-400">
							This VaporRAM engine is shared on a network.
						</p>
					</div>
				</div>

				<p className="text-sm text-slate-400 mb-4">
					Run{" "}
					<code className="rounded bg-slate-800 px-1.5 py-0.5 text-cyan-400">
						vapor share
					</code>{" "}
					on the machine hosting the model to see its key.
				</p>

				<div className="flex gap-2">
					<div className="relative flex-1">
						<KeyRound className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
						<Input
							autoFocus
							value={value}
							onChange={(e) => setValue(e.target.value)}
							onKeyDown={(e) => {
								if (e.key === "Enter") submit();
							}}
							placeholder="vr_..."
							className="pl-9 bg-slate-950 border-slate-700 font-mono text-sm"
							aria-label="API key"
						/>
					</div>
					<Button onClick={submit} disabled={checking || !value.trim()}>
						{checking ? (
							<Loader2 className="h-4 w-4 animate-spin" />
						) : (
							"Connect"
						)}
					</Button>
				</div>

				{error && (
					<p className="mt-3 text-sm text-red-400" role="alert">
						{error}
					</p>
				)}
			</div>
		</div>
	);
}
