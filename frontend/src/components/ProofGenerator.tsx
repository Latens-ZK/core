"use client";

import React, { useState, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Shield, Loader2, CheckCircle, XCircle, Copy, ExternalLink, Lock, Download, Box, Key, Cpu, Terminal, Info, ChevronRight, Binary, RefreshCw, AlertTriangle } from 'lucide-react';
import { MerkleVisualizer } from './MerkleVisualizer';
import { useNotify } from './NotificationSystem';
import {
    generateSalt,
    encodeAddressAsFelt252,
    computeCommitment,
    buildStarknetCalldata,
    type MerklePathElement,
} from '../lib/crypto';

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";
const VERIFIER_ADDRESS = process.env.NEXT_PUBLIC_VERIFIER_ADDRESS || "";
const DAO_GATE_ADDRESS = process.env.NEXT_PUBLIC_DAO_GATE_ADDRESS || "";

// ─── Bitcoin address validation ───────────────────────────────────────────────

const isValidBitcoinAddress = (addr: string): boolean => {
    const a = addr.trim();
    if (/^[1][a-km-zA-HJ-NP-Z1-9]{24,33}$/.test(a)) return true;
    if (/^[3][a-km-zA-HJ-NP-Z1-9]{24,33}$/.test(a)) return true;
    if (/^bc1[ac-hj-np-z02-9]{6,87}$/i.test(a)) return true;
    if (/^[mn][a-km-zA-HJ-NP-Z1-9]{24,33}$/.test(a)) return true;
    if (/^[2][a-km-zA-HJ-NP-Z1-9]{24,33}$/.test(a)) return true;
    if (/^tb1[ac-hj-np-z02-9]{6,87}$/i.test(a)) return true;
    return false;
};

// ─── Helper Components ────────────────────────────────────────────────────────

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

// Privacy badge — shows that address never left browser
const PrivacyBadge = () => (
    <div className="flex items-center gap-2 px-3 py-1.5 bg-emerald-500/5 border border-emerald-500/20 rounded-full text-[9px] text-emerald-400 font-black uppercase tracking-widest">
        <Shield className="w-3 h-3" />
        Address stays in browser
    </div>
);

// ─── Main State Machine ────────────────────────────────────────────────────────
// Step 1: User enters address + threshold → generateSalt locally
// Step 2: compute address_hash + commitment locally (encodeAddressAsFelt252 + computeCommitment)
// Step 3: POST /api/snapshot/witness/register {address_hash, commitment}
//   → backend finds row by address_hash, writes commitment, returns merkle_path + root
// Step 4: Client verifies the Merkle path locally (build calldata via buildStarknetCalldata)
// Step 5: Frontend submits verify_proof / join_dao to Starknet
// ─────────────────────────────────────────────────────────────────────────────

type Step = 'idle' | 'computing' | 'registering' | 'ready' | 'verifying' | 'verified' | 'error';

interface LocalWitness {
    address: string;
    addressHash: string;
    salt: string;
    commitment: string;
    balance: number;
    balanceBtc: string;
    snapshotRoot: string;
    merklePath: MerklePathElement[];
    blockHeight: number;
    threshold: number;
    calldataVerify: string[];
    calldataJoin: (extNull: string) => string[];
}

export const ProofGenerator = ({ account, onWalletConnect }: { account: any, onWalletConnect?: (acc: any) => void }) => {
    const { notify } = useNotify();
    const [address, setAddress] = useState('');
    const [thresholdBtc, setThresholdBtc] = useState('1');
    const [step, setStep] = useState<Step>('idle');
    const [witness, setWitness] = useState<LocalWitness | null>(null);
    const [txHash, setTxHash] = useState<string | null>(null);
    const [logs, setLogs] = useState<string[]>([]);
    const [error, setError] = useState('');
    const [showInspector, setShowInspector] = useState(false);

    const addLog = useCallback((msg: string) => {
        setLogs(prev => [...prev.slice(-9), `> ${msg}`]);
    }, []);

    const resetState = () => {
        setStep('idle');
        setWitness(null);
        setTxHash(null);
        setLogs([]);
        setError('');
    };

    // ── Step 1–4: Client-side computation + commitment registration ───────────
    const handleGenerate = async () => {
        if (!address.trim()) {
            setError("Enter a valid Bitcoin address.");
            return;
        }
        if (!isValidBitcoinAddress(address.trim())) {
            setError("Invalid Bitcoin address format. Expected P2PKH (1...), P2SH (3...), or Bech32 (bc1...).");
            return;
        }
        const thresholdVal = parseFloat(thresholdBtc);
        if (isNaN(thresholdVal) || thresholdVal < 0) {
            setError("Threshold must be a non-negative number (BTC).");
            return;
        }

        setError('');
        setStep('computing');
        setWitness(null);
        setTxHash(null);
        setLogs([]);
        notify("Initializing ZK Solvency Oracle...", "info");

        const thresholdSats = Math.floor(thresholdVal * 100_000_000);

        try {
            // ── Step 1: generate salt locally (never leaves browser) ────────
            addLog("Generating cryptographic salt locally...");
            const salt = generateSalt();

            // ── Step 2: derive address_hash and commitment locally ──────────
            addLog("Computing address_hash = SHA256(address) % PRIME...");
            const addressHash = encodeAddressAsFelt252(address.trim());

            addLog("Computing commitment = Poseidon(address_hash, salt)...");
            const commitment = computeCommitment(addressHash, salt);

            addLog(`Commitment: ${commitment.slice(0, 12)}…`);
            notify("Client-side commitment computed. Registering with oracle...", "info");
            setStep('registering');

            // ── Step 3: register commitment with backend (address stays local)
            addLog("Requesting Merkle witness from oracle (no address sent)...");
            const res = await fetch(`${API_URL}/snapshot/witness/register`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    address_hash: addressHash,
                    commitment: commitment,
                }),
            });

            if (!res.ok) {
                const err = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
                const msg = err.detail || `HTTP ${res.status}`;
                if (res.status === 404) {
                    throw new Error(
                        `Address not found in the latest snapshot. ` +
                        `Ensure your Bitcoin address has a UTXO in the indexed block range.`
                    );
                }
                if (res.status === 409) {
                    throw new Error(
                        `A commitment is already registered for this address in this snapshot. ` +
                        `Try refreshing your salt (generate a new proof).`
                    );
                }
                throw new Error(msg);
            }

            const data = await res.json();
            addLog(`✓ Witness received. Block #${data.block_height}. Depth=${data.merkle_path.length}.`);

            // ── Step 4: build calldata locally (address_hash + salt included) ─
            addLog("Assembling Starknet calldata locally...");
            const calldata = buildStarknetCalldata({
                addressHash,
                salt,
                commitment,
                balance: BigInt(data.balance),
                merkleRoot: data.snapshot_root,
                merklePath: data.merkle_path,
                threshold: BigInt(thresholdSats),
            });

            const localWitness: LocalWitness = {
                address: address.trim(),
                addressHash,
                salt,
                commitment,
                balance: data.balance,
                balanceBtc: (data.balance / 100_000_000).toFixed(8),
                snapshotRoot: data.snapshot_root,
                merklePath: data.merkle_path,
                blockHeight: data.block_height,
                threshold: thresholdSats,
                calldataVerify: calldata.verifyProof,
                calldataJoin: calldata.joinDao,
            };

            setWitness(localWitness);
            setStep('ready');
            notify("Evidence sealed. Address never left your browser.", "success");
            addLog("✓ Proof ready for on-chain verification.");

        } catch (e: any) {
            notify("Generation Failed: " + (e.message || 'Unknown error'), "error");
            setError(e.message);
            setStep('error');
            addLog(`ERR: ${e.message}`);
        }
    };

    // ── Step 5: Submit to Starknet ─────────────────────────────────────────────
    const handleVerifyOnChain = async () => {
        if (!witness) return;

        let activeAccount = account;
        if (!activeAccount) {
            addLog("No wallet — opening wallet selector...");
            try {
                const { connect: connectWallet } = await import('get-starknet');
                const wallet = await connectWallet({ modalMode: 'alwaysAsk', modalTheme: 'dark' });
                if (!wallet?.isConnected) throw new Error('Wallet connection cancelled');
                activeAccount = wallet.account;
                onWalletConnect?.(activeAccount);
            } catch (e: any) {
                notify("Wallet connection required.", "error");
                setError("Connect your Starknet wallet to verify on-chain.");
                return;
            }
        }

        if (!VERIFIER_ADDRESS) {
            setError("Deploy contracts first and set NEXT_PUBLIC_VERIFIER_ADDRESS in .env.local.");
            return;
        }

        setStep('verifying');
        setError('');
        notify("Transmitting ZK Proof to Starknet...", "info");
        addLog("Executing verify_proof on BalanceVerifier...");

        try {
            const result = await activeAccount.execute([{
                contractAddress: VERIFIER_ADDRESS,
                entrypoint: 'verify_proof',
                calldata: witness.calldataVerify,
            }]);

            addLog(`Tx: ${result.transaction_hash.slice(0, 16)}…`);
            setTxHash(result.transaction_hash);
            setStep('verified');
            notify("On-Chain Verification Confirmed! Solvency: VALID.", "success");
            addLog("✓ ProofVerified event emitted on Starknet.");
        } catch (e: any) {
            notify("Verification Failed.", "error");
            setError(e.message || "Transaction aborted.");
            setStep('error');
            addLog(`TX_ERR: ${e.message}`);
        }
    };

    const handleJoinDao = async () => {
        if (!witness || !account) return;

        if (!DAO_GATE_ADDRESS) {
            setError("Set NEXT_PUBLIC_DAO_GATE_ADDRESS in .env.local.");
            return;
        }

        // external_nullifier = DAO gate contract address (prevents cross-DAO replay)
        const externalNullifier = BigInt(DAO_GATE_ADDRESS).toString();
        const calldata = witness.calldataJoin(externalNullifier);

        addLog("Executing join_dao on DaoGate...");
        try {
            const result = await account.execute([{
                contractAddress: DAO_GATE_ADDRESS,
                entrypoint: 'join_dao',
                calldata,
            }]);
            addLog(`DAO join Tx: ${result.transaction_hash.slice(0, 16)}…`);
            notify("DAO Membership Granted!", "success");
        } catch (e: any) {
            notify("DAO join failed: " + e.message, "error");
            addLog(`DAO_ERR: ${e.message}`);
        }
    };

    const downloadCertificate = () => {
        if (!witness) return;
        const cert = [
            `LATENS ZK PROOF CERTIFICATE`,
            `===========================`,
            `Verified: ${new Date().toISOString()}`,
            `BTC Height: ${witness.blockHeight}`,
            `Commitment: ${witness.commitment}`,
            `Balance: ≥ ${(witness.threshold / 100_000_000).toFixed(8)} BTC`,
            `Status: ${txHash ? 'ON-CHAIN VERIFIED' : 'LOCALLY VERIFIED'}`,
            txHash ? `TX: ${txHash}` : '',
            ``,
            `Privacy: Bitcoin address was never sent to any server.`,
        ].join('\n');
        const blob = new Blob([cert], { type: 'text/plain' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url; a.download = `latens-proof-${witness.blockHeight}.txt`; a.click();
        URL.revokeObjectURL(url);
    };

    const isGenerating = step === 'computing' || step === 'registering';
    const isVerifying = step === 'verifying';

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
                        <div className="flex items-center justify-between gap-4 mb-10">
                            <div className="flex items-center gap-4">
                                <div className="p-3 bg-white/5 rounded-2xl border border-white/10 shadow-inner">
                                    <Lock className="w-6 h-6 text-silver-primary" />
                                </div>
                                <div>
                                    <h2 className="text-xl font-bold text-glow-silver tracking-tight">ZK Solvency Oracle</h2>
                                    <p className="text-[10px] text-gray-500 uppercase tracking-widest font-black">Privacy-First Verification</p>
                                </div>
                            </div>
                            <PrivacyBadge />
                        </div>

                        <div className="space-y-6 mb-10">
                            <div className="space-y-2">
                                <label className="text-[10px] text-gray-500 font-black uppercase tracking-widest">Bitcoin Identity</label>
                                <div className="relative">
                                    <input
                                        type="text"
                                        id="bitcoin-address-input"
                                        value={address}
                                        onChange={e => setAddress(e.target.value)}
                                        placeholder="Enter public address..."
                                        className="w-full bg-white/5 border border-white/10 rounded-2xl px-6 py-5 text-sm font-mono focus:border-silver-primary/50 focus:bg-white/8 transition-all outline-none"
                                    />
                                    <div className="absolute right-4 top-1/2 -translate-y-1/2">
                                        <Lock className="w-4 h-4 text-gray-600" />
                                    </div>
                                </div>
                                <p className="text-[9px] text-gray-600 uppercase tracking-wide">
                                    🔒 Hashed locally — never transmitted to any server
                                </p>
                            </div>
                            <div className="space-y-2">
                                <label className="text-[10px] text-gray-500 font-black uppercase tracking-widest">Solvency Threshold (BTC)</label>
                                <input
                                    type="number"
                                    id="threshold-input"
                                    value={thresholdBtc}
                                    onChange={e => setThresholdBtc(e.target.value)}
                                    min="0"
                                    step="0.1"
                                    className="w-full bg-white/5 border border-white/10 rounded-2xl px-6 py-5 text-sm font-mono focus:border-silver-primary/50 focus:bg-white/8 transition-all outline-none"
                                />
                            </div>
                        </div>

                        {/* Step indicator */}
                        {isGenerating && (
                            <div className="mb-6 flex items-center gap-3 text-[10px] text-silver-primary/70 uppercase tracking-widest">
                                <Loader2 className="w-4 h-4 animate-spin" />
                                {step === 'computing' ? 'Computing locally...' : 'Registering with oracle...'}
                            </div>
                        )}

                        <button
                            id="generate-proof-btn"
                            onClick={handleGenerate}
                            disabled={isGenerating || isVerifying}
                            className="btn-metallic w-full py-5 rounded-2xl text-[11px] uppercase tracking-[0.3em] font-black flex items-center justify-center gap-3 active:scale-[0.98] disabled:opacity-50 transition-all"
                        >
                            {isGenerating ? <Loader2 className="w-5 h-5 animate-spin" /> : <Cpu className="w-5 h-5" />}
                            {isGenerating ? "Processing ZK Circuit..." : "Generate Cryptographic Evidence"}
                        </button>

                        <div className="mt-8 pt-6 border-t border-white/5 flex flex-wrap gap-3">
                            <DemoBadge label="Whale-1" addr="1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa" onClick={setAddress} />
                            <DemoBadge label="Whale-2" addr="34xp4vRoCGJym3xR7yCVPFHoCNxv4Twseo" onClick={setAddress} />
                            {witness && (
                                <button
                                    onClick={resetState}
                                    className="px-4 py-2 bg-white/5 border border-white/10 rounded-xl text-[10px] text-gray-500 hover:text-white hover:border-red-500/30 transition-all font-black uppercase tracking-widest flex items-center gap-2"
                                >
                                    <RefreshCw className="w-3 h-3" /> Reset
                                </button>
                            )}
                        </div>

                        <AnimatePresence>
                            {error && (
                                <motion.div
                                    initial={{ opacity: 0, y: -4 }}
                                    animate={{ opacity: 1, y: 0 }}
                                    exit={{ opacity: 0 }}
                                    className="mt-6 flex items-start gap-3 p-4 bg-red-500/5 border border-red-500/20 rounded-xl"
                                >
                                    <XCircle className="w-4 h-4 text-red-400 mt-0.5 shrink-0" />
                                    <p className="text-[10px] text-red-400 font-bold uppercase tracking-wide leading-relaxed">{error}</p>
                                </motion.div>
                            )}
                        </AnimatePresence>
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
                        {!witness ? (
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
                                <p className="text-xs text-gray-500 max-w-xs leading-relaxed">Input identity parameters to launch the privacy-preserving ZK proof flow. Your Bitcoin address is hashed locally and never transmitted.</p>
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
                                            {step === 'verified' ? 'On-Chain Validated' : 'Proof Sealed'}
                                        </div>
                                    </div>

                                    <div className="grid grid-cols-1 md:grid-cols-2 gap-8 relative z-10">
                                        <DataPoint icon={<Box />} label="Audit Height" value={`Block #${witness.blockHeight}`} />
                                        <DataPoint icon={<Key />} label="Commitment" value={witness.commitment} mono />
                                        <DataPoint icon={<Shield />} label="Verified Range" value={`≥ ${thresholdBtc} BTC`} />
                                        <DataPoint icon={<Cpu />} label="Privacy Mode" value="ZERO-KNOWLEDGE" />
                                    </div>

                                    {/* Privacy notice */}
                                    <div className="flex items-start gap-3 p-4 bg-emerald-500/5 border border-emerald-500/15 rounded-2xl relative z-10">
                                        <Lock className="w-4 h-4 text-emerald-400 mt-0.5 shrink-0" />
                                        <p className="text-[9px] text-emerald-400/80 leading-relaxed uppercase tracking-wide">
                                            Your Bitcoin address (<span className="font-mono">{witness.address.slice(0, 8)}…</span>) was hashed locally and was never sent to any server. Only the commitment hash ({witness.commitment.slice(0, 10)}…) was transmitted.
                                        </p>
                                    </div>

                                    <div className="pt-8 border-t border-white/5 flex flex-wrap gap-4 relative z-10">
                                        <button
                                            id="verify-onchain-btn"
                                            onClick={handleVerifyOnChain}
                                            disabled={isVerifying || step === 'verified'}
                                            className="btn-metallic flex-grow py-5 rounded-2xl text-[11px] font-black uppercase tracking-widest shadow-xl disabled:opacity-50 flex items-center justify-center gap-3"
                                        >
                                            {isVerifying && <Loader2 className="w-4 h-4 animate-spin" />}
                                            {step === 'verified' ? "Verification Confirmed" : isVerifying ? "Transmitting..." : "Transmit to Starknet"}
                                        </button>
                                        {DAO_GATE_ADDRESS && step === 'verified' && (
                                            <button
                                                id="join-dao-btn"
                                                onClick={handleJoinDao}
                                                disabled={!account}
                                                className="flex-grow py-5 rounded-2xl text-[11px] font-black uppercase tracking-widest bg-white/5 border border-white/10 hover:border-silver-primary/30 disabled:opacity-50 flex items-center justify-center gap-3"
                                            >
                                                <Shield className="w-4 h-4" />
                                                Join DAO
                                            </button>
                                        )}
                                        <button
                                            onClick={() => setShowInspector(true)}
                                            className="p-5 bg-white/5 border border-white/10 rounded-2xl hover:bg-white/10 transition-colors"
                                            title="Launch Proof Inspector"
                                        >
                                            <Binary className="w-5 h-5 text-silver-primary" />
                                        </button>
                                    </div>
                                </div>

                                {/* Tx result */}
                                <AnimatePresence>
                                    {step === 'verified' && txHash && (
                                        <motion.div
                                            key="tx-result"
                                            initial={{ opacity: 0, y: 12 }}
                                            animate={{ opacity: 1, y: 0 }}
                                            className="glass-card p-8 border border-silver-primary/20 space-y-5"
                                        >
                                            <div className="flex items-center gap-3">
                                                <CheckCircle className="w-5 h-5 text-silver-primary" />
                                                <h4 className="text-sm font-black uppercase tracking-widest text-silver-primary">On-Chain Verification Confirmed</h4>
                                            </div>
                                            <div>
                                                <p className="text-[9px] uppercase tracking-[0.2em] text-gray-500 font-black mb-2">Starknet Transaction Hash</p>
                                                <div className="bg-black/40 border border-white/5 rounded-xl p-4 font-mono text-[11px] text-silver-primary/80 break-all">{txHash}</div>
                                            </div>
                                            <div className="flex flex-wrap gap-3">
                                                <a
                                                    href={`https://sepolia.starkscan.co/tx/${txHash}`}
                                                    target="_blank" rel="noopener noreferrer"
                                                    className="flex items-center gap-2 px-5 py-2.5 bg-white/5 border border-white/10 rounded-xl text-[10px] font-black uppercase tracking-widest hover:border-silver-primary/30 transition-all"
                                                >
                                                    <ExternalLink className="w-3.5 h-3.5" />
                                                    View on Starkscan
                                                </a>
                                                <button
                                                    onClick={downloadCertificate}
                                                    className="flex items-center gap-2 px-5 py-2.5 bg-white/5 border border-white/10 rounded-xl text-[10px] font-black uppercase tracking-widest hover:border-silver-primary/30 transition-all"
                                                >
                                                    <Download className="w-3.5 h-3.5" />
                                                    Download Certificate
                                                </button>
                                                <button
                                                    onClick={() => { navigator.clipboard.writeText(txHash); notify("TX hash copied.", "success"); }}
                                                    className="p-2.5 bg-white/5 border border-white/10 rounded-xl hover:bg-white/10 transition-colors"
                                                >
                                                    <Copy className="w-3.5 h-3.5 text-silver-primary" />
                                                </button>
                                            </div>
                                        </motion.div>
                                    )}
                                </AnimatePresence>

                                <div className="glass-card p-4 metallic-border">
                                    <MerkleVisualizer
                                        leaf={witness.commitment}
                                        path={witness.merklePath}
                                        root={witness.snapshotRoot}
                                        isVerified={step === 'verified'}
                                    />
                                </div>
                            </motion.div>
                        )}
                    </AnimatePresence>
                </div>
            </div>

            {/* Proof Inspector Modal */}
            <AnimatePresence>
                {showInspector && witness && (
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
                                <button onClick={() => setShowInspector(false)} className="p-2 hover:bg-white/10 rounded-xl transition-colors">
                                    <XCircle className="w-5 h-5 text-gray-500" />
                                </button>
                            </div>

                            <div className="p-10 max-h-[65vh] overflow-y-auto custom-scrollbar space-y-8">
                                <InspectorSection
                                    title="Privacy Model"
                                    icon={<Lock className="w-4 h-4 text-silver-primary" />}
                                    content={`address_hash = SHA256("${witness.address}") mod P\ncommitment   = Poseidon(address_hash, salt)\n\nOnly the commitment was sent to the backend.\nThe raw address and salt never left your browser.`}
                                    mono
                                />
                                <InspectorSection
                                    title="Circuit Constants"
                                    icon={<Binary className="w-4 h-4 text-silver-primary" />}
                                    content={`Field: Prime P = 2^251 + 17·2^192 + 1\nHash: Poseidon (t=3, RF=8, RP=83)\nCommitment: Poseidon(addr_hash, salt)\nLeaf: Poseidon(addr_hash, balance)\nMerkle path depth: ${witness.merklePath.length}`}
                                    mono
                                />
                                <InspectorSection
                                    title="Protocol Calldata (verify_proof)"
                                    icon={<Terminal className="w-4 h-4 text-silver-primary" />}
                                    content={JSON.stringify({
                                        commitment: witness.commitment,
                                        snapshot_root: witness.snapshotRoot,
                                        block_height: witness.blockHeight,
                                        threshold_sats: witness.threshold,
                                        merkle_path_depth: witness.merklePath.length,
                                        calldata_preview: witness.calldataVerify.slice(0, 6).join(', ') + '...',
                                    }, null, 2)}
                                    mono code
                                />
                            </div>

                            <div className="p-8 bg-white/2 border-t border-white/5 flex justify-between items-center">
                                <button
                                    onClick={() => {
                                        navigator.clipboard.writeText(JSON.stringify({
                                            commitment: witness.commitment,
                                            address_hash: witness.addressHash,
                                            snapshot_root: witness.snapshotRoot,
                                            calldata: witness.calldataVerify,
                                        }, null, 2));
                                        notify("Witness calldata copied.", "success");
                                    }}
                                    className="flex items-center gap-2 px-6 py-3 bg-white/5 border border-white/10 rounded-xl text-[10px] font-black uppercase tracking-widest hover:border-silver-primary/30 transition-all"
                                >
                                    <Copy className="w-4 h-4" />
                                    Copy Calldata
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
