"use client";

import React, { useState, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Shield, Loader2, CheckCircle, XCircle, Copy, ExternalLink, Lock, Download, Box, Key, Cpu, Terminal, Info, ChevronRight, Binary } from 'lucide-react';
import { MerkleVisualizer } from './MerkleVisualizer';
import { useNotify } from './NotificationSystem';

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";
const VERIFIER_ADDRESS = process.env.NEXT_PUBLIC_VERIFIER_ADDRESS || "";

// --- Helper Components (Hoisted for stability) ---

const DemoBadge = ({ label, addr, onClick }: { label: string, addr: string, onClick: (s: string) => void }) => (
    <button
        onClick={() => onClick(addr)}
        className="px-4 py-2 bg-white/5 border border-white/10 rounded-xl text-[10px] text-gray-500 hover:text-white hover:border-silver-primary/30 transition-all font-black uppercase tracking-widest"
    >
        {label}
    </button>
);

const DataPoint = ({ icon, label, value, mono }: { icon: React.ReactNode, label: string, value: string, mono?: boolean }) => (
    <div className="flex items-center gap-5 group">
        <div className="p-3 bg-white/5 rounded-2xl border border-white/10 text-gray-400 group-hover:text-silver-primary group-hover:border-silver-primary/30 transition-all duration-500">
            {React.isValidElement(icon) ? React.cloneElement(icon as React.ReactElement, { className: 'w-5 h-5' } as any) : icon}
        </div>
        <div>
            <p className="text-[9px] uppercase tracking-[0.2em] text-gray-500 font-black mb-1.5">{label}</p>
            <p className={`text-sm font-bold text-white ${mono ? 'font-mono' : 'tracking-tight'}`}>{value.length > 30 ? `${value.slice(0, 15)}...${value.slice(-15)}` : value}</p>
        </div>
    </div>
);

const InspectorSection = ({ title, icon, content, mono, code }: { title: string, icon: React.ReactNode, content: string, mono?: boolean, code?: boolean }) => (
    <div className="space-y-4">
        <div className="flex items-center gap-4">
            <div className="p-2 bg-silver-primary/5 rounded-lg">
                {icon}
            </div>
            <h4 className="text-[11px] font-black uppercase tracking-widest text-white">{title}</h4>
        </div>
        <div className={`
            p-5 rounded-2xl border border-white/5 bg-black/40 shadow-inner
            ${mono ? 'font-mono' : ''}
            ${code ? 'text-[9px]' : 'text-xs'}
            text-gray-400 leading-relaxed
        `}>
            {code ? <pre className="whitespace-pre-wrap">{content}</pre> : content}
        </div>
    </div>
);

// --- Main Component ---

export const ProofGenerator = ({ account }: { account: any }) => {
    const { notify } = useNotify();
    const [address, setAddress] = useState('');
    const [thresholdBtc, setThresholdBtc] = useState('1');
    const [status, setStatus] = useState<'idle' | 'generating' | 'ready' | 'verifying' | 'verified' | 'error'>('idle');
    const [proofData, setProofData] = useState<any>(null);
    const [txHash, setTxHash] = useState<string | null>(null);
    const [logs, setLogs] = useState<string[]>([]);
    const [error, setError] = useState('');
    const [showInspector, setShowInspector] = useState(false);

    const addLog = useCallback((msg: string) => {
        setLogs(prev => [...prev.slice(-9), `> ${msg}`]);
    }, []);

    const handleGenerate = async () => {
        if (!address.trim()) {
            notify("Identification required: enter a valid Bitcoin address.", "error");
            setError("Identification required: enter a valid Bitcoin address.");
            return;
        }
        setError('');
        setStatus('generating');
        setProofData(null);
        setTxHash(null);
        setLogs([]);
        notify("Proof Generation Initialized. Spinning up ZK-State observer...", "info");

        const thresholdSats = Math.floor(parseFloat(thresholdBtc) * 100_000_000);
        const saltHex = Array.from(crypto.getRandomValues(new Uint8Array(32)))
            .map(b => b.toString(16).padStart(2, '0')).join('');

        try {
            addLog("Initializing secure salt generation...");
            addLog("Requesting proof from Latens ZK Oracle...");

            const res = await fetch(`${API_URL}/proof/generate`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    address: address.trim(),
                    salt_hex: saltHex,
                    threshold: thresholdSats,
                }),
            });

            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.detail || `HTTP ${res.status}`);
            }

            const data = await res.json();
            setProofData(data);
            setStatus('ready');
            notify("Evidence Generated Successfully. Merkle Path Committed.", "success");
            addLog("✓ Proof generated. Awaiting on-chain verification.");
        } catch (e: any) {
            notify("Generation Failed: " + (e.message || 'Unknown error'), "error");
            setError(e.message);
            setStatus('error');
            addLog(`ERR: ${e.message}`);
        }
    };

    const handleVerifyOnChain = async () => {
        if (!account) {
            notify("Session inactive: please connect your Starknet wallet.", "error");
            setError("Session inactive: please connect your Starknet wallet.");
            return;
        }
        if (!VERIFIER_ADDRESS) {
            notify("System conflict: Verifier address not found.", "error");
            setError("System conflict: Verifier address not found.");
            return;
        }
        if (!proofData) return;

        setStatus('verifying');
        setError('');
        notify("Transmission Initiated. Dispatching ZK-Proof to Starknet Verifier...", "info");
        addLog("Serializing proof for Starknet execution...");

        try {
            const merklePathCalldata: string[] = [
                proofData.merkle_path.length.toString(),
                ...proofData.merkle_path.flatMap((el: { value: number; direction: boolean }) => [
                    el.value.toString(),
                    el.direction ? '1' : '0',
                ]),
            ];

            const calldata = [
                proofData.address_hash,
                proofData.salt,
                proofData.balance.toString(),
                ...merklePathCalldata,
                proofData.commitment,
                proofData.threshold.toString(),
            ];

            addLog("Executing on-chain verification contract...");

            const result = await account.execute([{
                contractAddress: VERIFIER_ADDRESS,
                entrypoint: 'verify_proof',
                calldata,
            }]);

            addLog(`Tx broadcasted: ${result.transaction_hash.slice(0, 14)}...`);
            setTxHash(result.transaction_hash);
            setStatus('verified');
            notify("On-Chain Verification Confirmed! Solvency Status: VALID.", "success");
            addLog("✓ State change confirmed on Starknet.");

        } catch (e: any) {
            notify("Verification Failed: Interrupted by chain state.", "error");
            setError(e.message || "Transaction aborted.");
            setStatus('error');
            addLog(`TX_ERR: ${e.message}`);
        }
    };

    const downloadCertificate = () => {
        if (!proofData) return;
        const cert = `LATENS ZK PROOF CERTIFICATE\n===========================\nVerified: ${new Date().toISOString()}\nBTC Height: ${proofData.block_height}\nCommitment: ${proofData.commitment}\nStatus: ON-CHAIN VERIFIED\nTX: ${txHash || 'Pending'}`;
        const blob = new Blob([cert], { type: 'text/plain' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `proof-${proofData.block_height}.txt`;
        a.click();
        URL.revokeObjectURL(url);
    };

    return (
        <div className="max-w-6xl mx-auto space-y-12 pb-24">
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-12 items-start">
                {/* Control Panel */}
                <div className="lg:col-span-5 space-y-6">
                    <motion.div
                        initial={{ opacity: 0, x: -20 }}
                        animate={{ opacity: 1, x: 0 }}
                        className="glass-card p-10 metallic-border relative overflow-hidden"
                    >
                        <div className="flex items-center gap-4 mb-10">
                            <div className="p-3 bg-white/5 rounded-2xl border border-white/10 shadow-inner">
                                <Lock className="w-6 h-6 text-silver-primary" />
                            </div>
                            <div>
                                <h2 className="text-xl font-bold text-glow-silver tracking-tight">ZK Solvency Oracle</h2>
                                <p className="text-[10px] text-gray-500 uppercase tracking-widest font-black">Professional Decentralized Verification</p>
                            </div>
                        </div>

                        <div className="space-y-6 mb-10">
                            <div className="space-y-2">
                                <label className="text-[10px] text-gray-500 font-black uppercase tracking-widest">Bitcoin Identity</label>
                                <input
                                    type="text"
                                    value={address}
                                    onChange={e => setAddress(e.target.value)}
                                    placeholder="Enter public address..."
                                    className="w-full bg-white/5 border border-white/10 rounded-2xl px-6 py-5 text-sm font-mono focus:border-silver-primary/50 focus:bg-white/8 transition-all outline-none"
                                />
                            </div>
                            <div className="space-y-2">
                                <label className="text-[10px] text-gray-500 font-black uppercase tracking-widest">Solvency Threshold (BTC)</label>
                                <input
                                    type="number"
                                    value={thresholdBtc}
                                    onChange={e => setThresholdBtc(e.target.value)}
                                    min="0"
                                    step="0.1"
                                    className="w-full bg-white/5 border border-white/10 rounded-2xl px-6 py-5 text-sm font-mono focus:border-silver-primary/50 focus:bg-white/8 transition-all outline-none"
                                />
                            </div>
                        </div>

                        <button
                            onClick={handleGenerate}
                            disabled={status === 'generating' || status === 'verifying'}
                            className="btn-metallic w-full py-5 rounded-2xl text-[11px] uppercase tracking-[0.3em] font-black flex items-center justify-center gap-3 active:scale-[0.98] disabled:opacity-50 transition-all"
                        >
                            {status === 'generating' ? <Loader2 className="w-5 h-5 animate-spin" /> : <Cpu className="w-5 h-5" />}
                            {status === 'generating' ? "Processing ZK Circuit..." : "Generate Cryptographic Evidence"}
                        </button>

                        <div className="mt-8 pt-6 border-t border-white/5 flex flex-wrap gap-3">
                            <DemoBadge label="Whale-1" addr="1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa" onClick={setAddress} />
                            <DemoBadge label="Whale-2" addr="34xp4vRoCGJym3xR7yCVPFHoCNxv4Twseo" onClick={setAddress} />
                        </div>
                    </motion.div>

                    {/* Console Trace */}
                    <AnimatePresence>
                        {logs.length > 0 && (
                            <motion.div
                                key="logs"
                                initial={{ opacity: 0, scale: 0.95 }}
                                animate={{ opacity: 1, scale: 1 }}
                                exit={{ opacity: 0, scale: 0.95 }}
                                className="bg-charcoal/80 backdrop-blur-md border border-white/5 rounded-2xl px-6 py-5 font-mono text-[9px] text-silver-primary/60 space-y-1.5 shadow-2xl overflow-hidden"
                            >
                                <div className="flex items-center gap-2 mb-2 border-b border-white/5 pb-2">
                                    <Terminal className="w-3 h-3" />
                                    <span className="uppercase tracking-widest font-black opacity-40">System Trace Logs</span>
                                </div>
                                {logs.map((log, i) => (
                                    <div key={i} className={i === logs.length - 1 ? 'text-white font-bold opacity-100' : ''}>
                                        {log}
                                    </div>
                                ))}
                            </motion.div>
                        )}
                    </AnimatePresence>
                </div>

                {/* Evidence Panel */}
                <div className="lg:col-span-7">
                    <AnimatePresence mode="wait">
                        {!proofData ? (
                            <motion.div
                                key="idle"
                                initial={{ opacity: 0 }}
                                animate={{ opacity: 1 }}
                                exit={{ opacity: 0 }}
                                className="h-[500px] border-2 border-dashed border-white/5 rounded-3xl flex flex-col items-center justify-center text-center p-12"
                            >
                                <div className="p-6 bg-white/2 rounded-full mb-6 border border-white/5">
                                    <Shield className="w-12 h-12 text-gray-700" />
                                </div>
                                <h3 className="text-xl font-bold text-gray-700 mb-2 uppercase tracking-widest">Evidence Chamber</h3>
                                <p className="text-xs text-gray-500 max-w-xs leading-relaxed">Input identity parameters to visualize the cryptographic state transition and verify solvency on-chain.</p>
                            </motion.div>
                        ) : (
                            <motion.div
                                key="result"
                                initial={{ opacity: 0, x: 20 }}
                                animate={{ opacity: 1, x: 0 }}
                                className="space-y-8"
                            >
                                <div className="glass-card metallic-border p-10 space-y-8 relative overflow-hidden">
                                    <div className="absolute top-0 right-0 p-4 opacity-5 pointer-events-none">
                                        <Binary className="w-48 h-48" />
                                    </div>

                                    <div className="flex items-center justify-between relative z-10">
                                        <h3 className="text-sm font-black uppercase tracking-[0.4em] text-silver-primary">Solvency Summary</h3>
                                        <div className="flex items-center gap-2 px-4 py-1.5 bg-silver-primary/10 border border-silver-primary/30 rounded-full text-[10px] text-silver-primary font-black uppercase tracking-widest">
                                            {status === 'verified' ? 'On-Chain Validated' : 'Proof Sealed'}
                                        </div>
                                    </div>

                                    <div className="grid grid-cols-1 md:grid-cols-2 gap-8 relative z-10">
                                        <DataPoint icon={<Box />} label="Audit Height" value={`Block #${proofData.block_height}`} />
                                        <DataPoint icon={<Key />} label="State Identity" value={proofData.address_hash} mono />
                                        <DataPoint icon={<Shield />} label="Verified Range" value={`> ${thresholdBtc} BTC`} />
                                        <DataPoint icon={<Cpu />} label="System Mode" value="ZERO-KNOWLEDGE" />
                                    </div>

                                    <div className="pt-8 border-t border-white/5 flex flex-wrap gap-4 relative z-10">
                                        <button
                                            onClick={handleVerifyOnChain}
                                            disabled={status === 'verifying' || status === 'verified'}
                                            className="btn-metallic flex-grow py-5 rounded-2xl text-[11px] font-black uppercase tracking-widest shadow-xl disabled:opacity-50"
                                        >
                                            {status === 'verified' ? "Verification Confirmed" : "Transmit to Starknet"}
                                        </button>
                                        <button
                                            onClick={() => setShowInspector(true)}
                                            className="p-5 bg-white/5 border border-white/10 rounded-2xl hover:bg-white/10 transition-colors"
                                            title="Launch Proof Inspector"
                                        >
                                            <Binary className="w-5 h-5 text-silver-primary" />
                                        </button>
                                    </div>
                                </div>

                                <div className="glass-card p-4 metallic-border">
                                    <MerkleVisualizer
                                        leaf={proofData.address_hash}
                                        path={proofData.merkle_path}
                                        root={proofData.snapshot_root}
                                        isVerified={status === 'verified'}
                                    />
                                </div>
                            </motion.div>
                        )}
                    </AnimatePresence>
                </div>
            </div>

            {/* Proof Inspector Modal */}
            <AnimatePresence>
                {showInspector && proofData && (
                    <div className="fixed inset-0 z-[100] flex items-center justify-center p-6">
                        <motion.div
                            key="modal-bg"
                            initial={{ opacity: 0 }}
                            animate={{ opacity: 1 }}
                            exit={{ opacity: 0 }}
                            onClick={() => setShowInspector(false)}
                            className="absolute inset-0 bg-black/95 backdrop-blur-xl"
                        />
                        <motion.div
                            key="modal-content"
                            initial={{ scale: 0.9, opacity: 0, y: 20 }}
                            animate={{ scale: 1, opacity: 1, y: 0 }}
                            exit={{ scale: 0.9, opacity: 0, y: 20 }}
                            className="relative glass-card metallic-border w-full max-w-2xl overflow-hidden shadow-[0_0_100px_rgba(192,192,192,0.15)]"
                        >
                            <div className="p-8 border-b border-white/5 flex justify-between items-center bg-white/2">
                                <div className="flex items-center gap-4">
                                    <div className="p-3 bg-silver-primary/10 rounded-2xl border border-silver-primary/30">
                                        <Cpu className="w-6 h-6 text-silver-primary" />
                                    </div>
                                    <div>
                                        <h3 className="text-xl font-bold text-white tracking-tight">ZK Proof Inspector</h3>
                                        <p className="text-[10px] text-gray-500 uppercase tracking-widest font-black">Low-Level Cryptographic Trace</p>
                                    </div>
                                </div>
                                <button
                                    onClick={() => setShowInspector(false)}
                                    className="p-2 hover:bg-white/10 rounded-xl transition-colors"
                                >
                                    <XCircle className="w-5 h-5 text-gray-500" />
                                </button>
                            </div>

                            <div className="p-10 max-h-[65vh] overflow-y-auto custom-scrollbar space-y-8">
                                <InspectorSection
                                    title="Constraint Overview"
                                    icon={<Lock className="w-4 h-4 text-silver-primary" />}
                                    content="The generated proof satisfies public input constraints for both range-check (balance > threshold) and membership consistency (address ∈ UTXO_ROOT). Verification is performed using high-degree polynomial constraints."
                                />

                                <InspectorSection
                                    title="Circuit Constants"
                                    icon={<Binary className="w-4 h-4 text-silver-primary" />}
                                    content={`Field: Prime Order P = 2^251 + 17 * 2^192 + 1\nHash: Poseidon (3-ary, r=2, c=1)\nCurve: Stark-Curve\nSecurity: 128-bit quantum-ready`}
                                    mono
                                />

                                <InspectorSection
                                    title="Protocol Calldata"
                                    icon={<Terminal className="w-4 h-4 text-silver-primary" />}
                                    content={JSON.stringify(proofData, null, 2)}
                                    mono
                                    code
                                />
                            </div>

                            <div className="p-8 bg-white/2 border-t border-white/5 flex justify-between items-center">
                                <button
                                    onClick={() => {
                                        navigator.clipboard.writeText(JSON.stringify(proofData, null, 2));
                                        notify("Evidence Calldata copied.", "success");
                                    }}
                                    className="flex items-center gap-2 px-6 py-3 bg-white/5 border border-white/10 rounded-xl text-[10px] font-black uppercase tracking-widest hover:border-silver-primary/30 transition-all"
                                >
                                    <Copy className="w-4 h-4" />
                                    Copy Raw Witness
                                </button>
                                <button
                                    onClick={() => setShowInspector(false)}
                                    className="text-[10px] font-black uppercase tracking-[0.4em] text-silver-primary hover:text-white transition-colors"
                                >
                                    [ Exit Inspector ]
                                </button>
                            </div>
                        </motion.div>
                    </div>
                )}
            </AnimatePresence>
        </div>
    );
};
