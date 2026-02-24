"use client";

import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Radio, Activity, Terminal, CheckCircle2, Clock } from 'lucide-react';

export const StateRadar = () => {
    const [blocksProcessed, setBlocksProcessed] = useState(824500);
    const [isScanning, setIsScanning] = useState(true);

    useEffect(() => {
        const interval = setInterval(() => {
            setBlocksProcessed(prev => prev + (Math.random() > 0.8 ? 1 : 0));
        }, 3000);
        return () => clearInterval(interval);
    }, []);

    return (
        <div className="glass-card metallic-border p-8 mb-24 max-w-5xl mx-auto overflow-hidden relative">
            {/* Background Animation */}
            <div className="absolute top-0 right-0 w-64 h-64 bg-silver-primary/5 rounded-full blur-3xl -z-10 animate-pulse" />

            <div className="flex flex-col md:flex-row gap-8 items-center">
                <div className="relative w-48 h-48 flex-shrink-0">
                    {/* Radar Circles */}
                    <div className="absolute inset-0 border border-white/5 rounded-full" />
                    <div className="absolute inset-4 border border-white/10 rounded-full" />
                    <div className="absolute inset-10 border border-white/20 rounded-full" />

                    {/* Radar Sweep */}
                    <motion.div
                        animate={{ rotate: 360 }}
                        transition={{ duration: 4, repeat: Infinity, ease: "linear" }}
                        className="absolute inset-0 border-t-2 border-t-silver-primary/40 rounded-full origin-center"
                    />

                    {/* Center Icon */}
                    <div className="absolute inset-0 flex items-center justify-center">
                        <Radio className="w-8 h-8 text-silver-primary animate-pulse" />
                    </div>

                    {/* Ping Particles */}
                    <AnimatePresence>
                        {isScanning && Array.from({ length: 3 }).map((_, i) => (
                            <motion.div
                                key={i}
                                initial={{ scale: 0, opacity: 0.5 }}
                                animate={{ scale: 2, opacity: 0 }}
                                transition={{ duration: 2, repeat: Infinity, delay: i * 0.6 }}
                                className="absolute inset-0 border border-silver-primary rounded-full"
                            />
                        ))}
                    </AnimatePresence>
                </div>

                <div className="flex-grow space-y-6">
                    <div className="flex items-center justify-between">
                        <div>
                            <h3 className="text-[10px] font-black uppercase tracking-[0.4em] text-gray-600 mb-1">State Synchronizer</h3>
                            <h4 className="text-2xl font-bold text-white tracking-tight">Bitcoin Core Observer</h4>
                        </div>
                        <div className="flex items-center gap-3 px-4 py-2 bg-white/5 border border-white/10 rounded-xl">
                            <Activity className="w-4 h-4 text-silver-primary animate-pulse" />
                            <span className="text-[10px] font-bold text-silver-primary uppercase tracking-widest">Live Feed</span>
                        </div>
                    </div>

                    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                        <StatusItem icon={<Clock className="w-3.5 h-3.5" />} label="Avg Block Time" value="9.8 min" />
                        <StatusItem icon={<Terminal className="w-3.5 h-3.5" />} label="State Root" value="0x5f...a231" />
                        <StatusItem icon={<CheckCircle2 className="w-3.5 h-3.5" />} label="Verified Range" value="824k - 825k" />
                        <StatusItem icon={<Activity className="w-3.5 h-3.5" />} label="Sync Integrity" value="99.99%" />
                    </div>

                    <div className="pt-4 border-t border-white/5">
                        <div className="flex justify-between items-end mb-2">
                            <p className="text-[9px] text-gray-500 font-bold uppercase tracking-widest">Consensus Finalization</p>
                            <p className="text-[11px] font-mono text-silver-primary">Height: {blocksProcessed.toLocaleString()}</p>
                        </div>
                        <div className="w-full h-1.5 bg-white/5 rounded-full overflow-hidden">
                            <motion.div
                                initial={{ width: "0%" }}
                                animate={{ width: "94.2%" }}
                                className="h-full bg-gradient-to-r from-silver-secondary to-silver-primary shadow-[0_0_10px_rgba(192,192,192,0.5)]"
                                transition={{ duration: 2 }}
                            />
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
};

const StatusItem = ({ icon, label, value }: { icon: React.ReactNode, label: string, value: string }) => (
    <div className="p-3 bg-white/5 rounded-xl border border-white/5">
        <div className="flex items-center gap-2 mb-1 text-gray-600">
            {icon}
            <span className="text-[8px] font-black uppercase tracking-widest">{label}</span>
        </div>
        <p className="text-xs font-bold text-white font-mono">{value}</p>
    </div>
);
