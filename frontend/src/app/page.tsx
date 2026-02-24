"use client";

import React from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Shield, ChevronRight, Binary } from 'lucide-react';
import { WalletConnect } from '../components/WalletConnect';
import { BackgroundEffect } from '../components/BackgroundEffect';
import { StatsBoard } from '../components/StatsBoard';
import { StateRadar } from '../components/StateRadar';
import { ErrorBoundary } from '../components/ErrorBoundary';

export default function Home() {
    const [account, setAccount] = React.useState<any>(null);

    const ProofGeneratorLazy = React.useMemo(() =>
        React.lazy(() =>
            import('../components/ProofGenerator').then(mod => ({ default: mod.ProofGenerator }))
        ),
        []
    );

    return (
        <main className="min-h-screen selection:bg-silver-primary/30 relative overflow-x-hidden">
            <BackgroundEffect />

            {/* Header */}
            <nav className="fixed top-0 w-full z-50 border-b border-white/5 bg-black/40 backdrop-blur-xl">
                <div className="max-w-7xl mx-auto px-6 h-20 flex items-center justify-between">
                    <div className="flex items-center gap-3">
                        <div className="p-2.5 bg-silver-primary/10 rounded-xl border border-silver-primary/20">
                            <Shield className="w-6 h-6 text-silver-primary" />
                        </div>
                        <div>
                            <h1 className="text-xl font-black tracking-tighter text-glow-silver">LATENS</h1>
                            <p className="text-[8px] uppercase tracking-[0.3em] text-gray-500 font-bold">ZK Solvency Layer</p>
                        </div>
                    </div>
                    <WalletConnect onConnect={(addr, acc) => setAccount(acc)} />
                </div>
            </nav>

            {/* Hero Section */}
            <div className="pt-40 pb-20 px-6">
                <div className="max-w-4xl mx-auto text-center mb-24">
                    <motion.div
                        initial={{ opacity: 0, scale: 0.9 }}
                        animate={{ opacity: 1, scale: 1 }}
                        className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-white/5 border border-white/10 text-[10px] text-silver-primary font-bold uppercase tracking-widest mb-8"
                    >
                        <div className="w-1.5 h-1.5 rounded-full bg-silver-primary animate-pulse shadow-[0_0_8px_rgba(192,192,192,0.8)]" />
                        Starknet x Bitcoin Interoperability
                    </motion.div>

                    <h2 className="text-5xl md:text-8xl font-black tracking-tight text-white mb-8 leading-[0.85]">
                        Verify Assets.<br />
                        <span className="text-silver-secondary">Privacy Intact.</span>
                    </h2>
                    <p className="text-gray-400 text-lg md:text-xl max-w-xl mx-auto font-medium leading-relaxed mb-12">
                        Latens uses Zero-Knowledge proofs to verify Bitcoin solvency on Starknet without ever exposing your private data.
                    </p>
                </div>

                <StateRadar />
                <StatsBoard />

                <div className="relative mt-24 mb-32">
                    <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-silver-primary/5 rounded-full blur-[120px] -z-10" />
                    <ErrorBoundary>
                        <React.Suspense fallback={
                            <div className="max-w-4xl mx-auto glass-card p-12 metallic-border text-center grayscale opacity-50">
                                <p className="text-xs uppercase tracking-[0.4em] animate-pulse">Synchronizing Cryptographic Modules...</p>
                            </div>
                        }>
                            <ProofGeneratorLazy account={account} />
                        </React.Suspense>
                    </ErrorBoundary>
                </div>

                {/* The Protocol Steps */}
                <div className="mt-40 max-w-6xl mx-auto">
                    <div className="flex flex-col md:flex-row items-center justify-between mb-16 gap-6">
                        <div>
                            <h3 className="text-[10px] font-black uppercase tracking-[0.4em] text-gray-600 mb-2">Technical Overview</h3>
                            <h4 className="text-3xl font-bold text-white tracking-tight">The ZK Verification Protocol</h4>
                        </div>
                        <div className="h-px flex-grow mx-8 bg-gradient-to-r from-white/10 to-transparent hidden md:block" />
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
                        <StepCard number="01" title="Aggregate" desc="We build a Merkle tree of the Bitcoin UTXO set at a specific block height." />
                        <StepCard number="02" title="Commit" desc="The State Root is registered on-chain via our Starknet Registry." />
                        <StepCard number="03" title="Generate" desc="You generate a client-side ZK proof of your balance and salt commitment." />
                        <StepCard number="04" title="Verify" desc="Starknet verifier confirms your proof against the registered state root." />
                    </div>
                </div>
            </div>

            <footer className="py-16 border-t border-white/5 bg-black/80 backdrop-blur-md">
                <div className="max-w-7xl mx-auto px-6 flex flex-col md:flex-row justify-between items-center gap-10">
                    <div className="flex items-center gap-4">
                        <div className="text-[10px] text-gray-600 font-bold uppercase tracking-[0.2em]">
                            LATENS PROTOCOL / 2024
                        </div>
                        <div className="w-1.5 h-1.5 rounded-full bg-white/5" />
                        <div className="text-[10px] text-gray-600 font-bold uppercase tracking-[0.2em]">
                            SECURED BY STARKNET
                        </div>
                    </div>
                    <div className="flex gap-12">
                        <FooterLink href="https://github.com" label="Core" />
                        <FooterLink href="https://starknet.io" label="Ecosystem" />
                        <FooterLink href="https://sepolia.starkscan.co" label="Scan" />
                    </div>
                </div>
            </footer>
        </main>
    );
}

const StepCard = ({ number, title, desc }: { number: string, title: string, desc: string }) => (
    <div className="glass-card metallic-border p-8 relative overflow-hidden group hover:scale-[1.02] transition-all duration-500">
        <div className="text-4xl font-black text-white/5 absolute -right-4 -bottom-4 group-hover:text-silver-primary/10 transition-colors uppercase italic tracking-tighter">{title}</div>
        <div className="text-xs font-black text-silver-primary mb-6 flex items-center gap-2">
            <span className="opacity-40">/</span>
            {number}
        </div>
        <h4 className="text-base font-bold text-white mb-3 uppercase tracking-wider">{title}</h4>
        <p className="text-[11px] text-gray-500 leading-relaxed font-semibold uppercase tracking-tight">{desc}</p>
    </div>
);

const FooterLink = ({ href, label }: { href: string, label: string }) => (
    <a href={href} className="text-[10px] text-gray-500 hover:text-silver-primary transition-colors font-bold uppercase tracking-[0.2em]">
        {label}
    </a>
);
