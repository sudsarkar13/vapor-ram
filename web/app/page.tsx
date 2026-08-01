"use client";

import React, { useState, useEffect } from "react";
import { Header, ActiveTab } from "@/components/Header";
import { Sidebar } from "@/components/Sidebar";
import { ChatView } from "@/components/ChatView";
import { BrainView } from "@/components/BrainView";
import { ProfilingView } from "@/components/ProfilingView";
import { DoctorView } from "@/components/DoctorView";
import {
	fetchHealth,
	fetchProgress,
	VaporMessage,
	VaporHealth,
	SystemProgress,
} from "@/lib/api";

export default function VaporDashboardPage() {
	const [activeTab, setActiveTab] = useState<ActiveTab>("chat");
	const [currentPreset, setPreset] = useState<string>("default");
	const [messages, setMessages] = useState<VaporMessage[]>([]);
	const [health, setHealth] = useState<VaporHealth | null>(null);
	const [progress, setProgress] = useState<SystemProgress | null>(null);
	const [isOnline, setIsOnline] = useState<boolean>(true);

	const checkHealthAndProgress = async () => {
		const h = await fetchHealth();
		if (h) {
			setHealth(h);
			setIsOnline(true);
		} else {
			setIsOnline(false);
		}

		const p = await fetchProgress();
		if (p) {
			setProgress(p);
		}
	};

	useEffect(() => {
		checkHealthAndProgress();
		const interval = setInterval(checkHealthAndProgress, 3000);
		return () => clearInterval(interval);
	}, []);

	const handleClearChat = () => {
		setMessages([]);
	};

	return (
		<div className="flex flex-col h-screen w-screen overflow-hidden bg-slate-950 text-slate-100 font-sans selection:bg-cyan-500 selection:text-slate-950">
			{/* Top Navigation Header */}
			<Header
				activeTab={activeTab}
				setActiveTab={setActiveTab}
				onClearChat={handleClearChat}
				isOnline={isOnline}
				activeModel={health?.active_model || "google/gemma-4-E4B-it"}
				slots={health?.slots || progress?.slots}
			/>

			{/* Main Workspace Body */}
			<div className="flex flex-col md:flex-row flex-1 overflow-hidden">
				{/* Left Telemetry & Controls Sidebar */}
				<Sidebar
					currentPreset={currentPreset}
					setPreset={setPreset}
					progress={progress}
					onRefreshHealth={checkHealthAndProgress}
				/>

				{/* Right Active View Content Area */}
				<main className="flex-1 overflow-hidden relative">
					{activeTab === "chat" && (
						<ChatView
							messages={messages}
							setMessages={setMessages}
							preset={currentPreset}
						/>
					)}

					{activeTab === "brain" && <BrainView />}

					{activeTab === "profiling" && <ProfilingView />}

					{activeTab === "doctor" && <DoctorView />}
				</main>
			</div>
		</div>
	);
}
