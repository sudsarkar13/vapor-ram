import type { Metadata, Viewport } from "next";
import {
	Geist,
	Geist_Mono,
	Noto_Sans,
	Playfair_Display,
} from "next/font/google";
import "./globals.css";
import { cn } from "@/lib/utils";

const playfairDisplayHeading = Playfair_Display({
	subsets: ["latin"],
	variable: "--font-heading",
});

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
	title: "VaporRAM — Ultra-Low RAM SSD Streaming LLM",
	description:
		"VaporRAM streams google/gemma-4-E4B-it directly from NVMe under a strict 1.5 GB RAM ceiling. C SIMD, O_DIRECT double-buffer, int8 KV cache.",
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
				playfairDisplayHeading.variable,
			)}>
			<body className="min-h-full flex flex-col">{children}</body>
		</html>
	);
}
