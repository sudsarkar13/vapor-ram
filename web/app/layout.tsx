import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono, Noto_Sans } from "next/font/google";
import "./globals.css";
import { cn } from "@/lib/utils";

const notoSans = Noto_Sans({ subsets: ["latin"], variable: "--font-sans" });

const geistSans = Geist({
	variable: "--font-geist-sans",
	subsets: ["latin"],
});

const geistMono = Geist_Mono({
	variable: "--font-geist-mono",
	subsets: ["latin"],
});

export const metadata: Metadata = {
	title: "VaporRAM — Local LLM Inference Server",
	description:
		"OpenAI-compatible local inference server, terminal chat client and dashboard for google/gemma-4-E4B-it. Token generation runs on llama.cpp; the dashboard reports only measured values.",
	applicationName: "VaporRAM",
	icons: {
		icon: [
			{ url: "/icon.svg", type: "image/svg+xml" },
			{ url: "/favicon.ico", sizes: "any" },
		],
		apple: "/icon.svg",
	},
};

// Next.js 15+ requires themeColor in its own viewport export.
export const viewport: Viewport = {
	themeColor: "#020617",
};

export default function RootLayout({
	children,
}: Readonly<{
	children: React.ReactNode;
}>) {
	return (
		<html
			lang="en"
			className={cn(
				"h-full",
				"antialiased",
				geistSans.variable,
				geistMono.variable,
				"font-sans",
				notoSans.variable,
			)}>
			<body className="min-h-full flex flex-col">{children}</body>
		</html>
	);
}
