"use client";

import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Wallet, LogOut, ChevronDown, Loader2 } from 'lucide-react';

interface WalletConnectProps {
    onConnect: (address: string, account: any) => void;
}

export const WalletConnect = ({ onConnect }: WalletConnectProps) => {
    const [address, setAddress] = useState<string | null>(null);
    const [connecting, setConnecting] = useState(false);
    const [error, setError] = useState('');

    const connect = async () => {
        setConnecting(true);
        setError('');
        try {
            const { connect: connectWallet, disconnect } = await import('get-starknet');
            const wallet = await connectWallet({
                modalMode: 'alwaysAsk',
                modalTheme: 'dark',
            });

            if (!wallet || !wallet.isConnected) {
                throw new Error('Wallet connection cancelled');
            }

            const acc = wallet.account;
            const addr = wallet.selectedAddress;

            setAddress(addr);
            onConnect(addr, acc);
        } catch (e: any) {
            setError(e.message);
        } finally {
            setConnecting(false);
        }
    };

    const disconnect = () => {
        setAddress(null);
        onConnect('', null);
        setError('');
    };

    if (address) {
        return (
            <motion.div
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                className="flex items-center gap-2"
            >
                <div className="flex items-center gap-3 bg-white/5 border border-white/10 rounded-xl px-4 py-2 shadow-inner">
                    <div className="w-1.5 h-1.5 rounded-full bg-silver-primary animate-pulse shadow-[0_0_8px_rgba(192,192,192,0.5)]" />
                    <span className="text-[10px] text-silver-primary font-bold tracking-widest font-mono">
                        {address.slice(0, 6)}...{address.slice(-4)}
                    </span>
                </div>
                <button
                    onClick={disconnect}
                    className="p-2.5 bg-white/5 border border-white/10 rounded-xl hover:bg-red-500/10 hover:border-red-500/20 transition-all group"
                    title="Terminate Session"
                >
                    <LogOut className="w-3.5 h-3.5 text-gray-500 group-hover:text-red-400 transition-colors" />
                </button>
            </motion.div>
        );
    }

    return (
        <div className="flex flex-col items-end gap-1">
            <motion.button
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
                onClick={connect}
                disabled={connecting}
                className="btn-metallic flex items-center gap-3 px-6 py-2.5 rounded-xl text-xs uppercase font-black tracking-widest active:scale-95 disabled:opacity-50"
            >
                {connecting ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                ) : (
                    <Wallet className="w-3.5 h-3.5 text-silver-primary" />
                )}
                <span>{connecting ? "Synchronizing..." : "Establish Interface"}</span>
            </motion.button>
            <AnimatePresence>
                {error && (
                    <motion.p
                        initial={{ opacity: 0, y: -4 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0 }}
                        className="text-[9px] text-red-400 font-bold uppercase tracking-wider mt-1"
                    >
                        {error}
                    </motion.p>
                )}
            </AnimatePresence>
        </div>
    );
};
