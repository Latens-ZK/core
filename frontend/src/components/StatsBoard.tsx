"use client";

import React, { useEffect, useState, useRef } from 'react';
import { motion, useSpring, useTransform, animate } from 'framer-motion';
import { Shield, Database, Activity } from 'lucide-react';

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

export const StatsBoard = () => {
    const [stats, setStats] = useState({
        total_snapshots: 0,
        latest_block_height: 0,
        total_btc_indexed: 0,
        protocol_status: "Connecting..."
    });
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const fetchStats = async () => {
            try {
                const res = await fetch(`${API_URL}/stats`);
                if (res.ok) {
                    const data = await res.json();
                    setStats(data);
                } else {
                    setStats(s => ({ ...s, protocol_status: "Offline" }));
                }
            } catch {
                setStats(s => ({ ...s, protocol_status: "Offline" }));
            } finally {
                setLoading(false);
            }
        };

        fetchStats();
        const interval = setInterval(fetchStats, 10000);
        return () => clearInterval(interval);
    }, []);

    const btcValue = stats.total_btc_indexed / 100_000_000;

    return (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8 w-full max-w-6xl mx-auto mb-24 px-4">
            <StatsCard
                icon={<Database className="w-5 h-5 text-silver-primary" />}
                label="Verified State Height"
                value={<CountingNumber value={stats.latest_block_height} prefix="#" />}
                subtext="Bitcoin Mainnet Sync"
            />
            <StatsCard
                icon={<Shield className="w-5 h-5 text-silver-primary" />}
                label="Proof-of-Solvency Capacity"
                value={<CountingNumber value={btcValue} decimals={2} suffix=" BTC" />}
                subtext="Locked in Poseidon Roots"
            />
            <StatsCard
                icon={<Activity className="w-5 h-5 text-silver-primary" />}
                label="Operational Status"
                value={loading ? "..." : stats.protocol_status.toUpperCase()}
                subtext={`Verified Evidence: ${stats.total_snapshots}`}
                statusColor={stats.protocol_status === "Offline" ? "text-red-500" : "text-white text-glow-silver"}
            />
        </div>
    );
};

const CountingNumber = ({ value, prefix = "", suffix = "", decimals = 0 }: { value: number, prefix?: string, suffix?: string, decimals?: number }) => {
    const [display, setDisplay] = useState(0);

    useEffect(() => {
        const controls = animate(display, value, {
            duration: 2,
            onUpdate: (latest) => setDisplay(latest)
        });
        return () => controls.stop();
    }, [value]);

    return (
        <span className="font-mono">
            {prefix}{display.toLocaleString(undefined, { minimumFractionDigits: decimals, maximumFractionDigits: decimals })}{suffix}
        </span>
    );
};

const StatsCard = ({ icon, label, value, subtext, statusColor }: {
    icon: React.ReactNode;
    label: string;
    value: React.ReactNode;
    subtext: string;
    statusColor?: string;
}) => (
    <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        whileHover={{ y: -8, scale: 1.02 }}
        className="glass-card metallic-border p-8 flex items-center gap-6 hover:border-silver-primary/30 transition-all shadow-[0_20px_40px_rgba(0,0,0,0.4)] relative group"
    >
        <div className="absolute inset-0 bg-gradient-to-br from-white/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity rounded-3xl" />

        <div className="p-4 bg-white/5 rounded-2xl border border-white/5 group-hover:border-silver-primary/20 transition-colors relative z-10 shrink-0">
            {icon}
        </div>

        <div className="min-w-0 relative z-10">
            <p className="text-[10px] text-gray-500 font-black uppercase tracking-[0.2em] mb-2">{label}</p>
            <div className={`text-2xl font-bold tracking-tight truncate ${statusColor || 'text-white'}`}>
                {value}
            </div>
            <p className="text-[10px] text-gray-600 font-bold uppercase tracking-widest mt-1 opacity-60">{subtext}</p>
        </div>
    </motion.div>
);
