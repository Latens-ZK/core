"use client";

import React from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Shield, Share2, GitBranch, Binary } from 'lucide-react';

interface MerklePathElement {
    value: string | number;
    direction: boolean;
}

interface MerkleVisualizerProps {
    leaf: string | number;
    path: MerklePathElement[];
    root: string | number;
    isVerified: boolean;
}

export const MerkleVisualizer = ({ leaf, path, root, isVerified }: MerkleVisualizerProps) => {
    // Generate nodes for the path
    // path is sorted from leaf to root

    return (
        <div className="glass-card p-6 metallic-border overflow-hidden">
            <div className="flex items-center gap-3 mb-6">
                <div className="p-2 bg-white/5 rounded-lg border border-white/10">
                    <Binary className="w-5 h-5 text-silver-primary" />
                </div>
                <div>
                    <h3 className="text-sm font-semibold text-white">Merkle Proof Path</h3>
                    <p className="text-[10px] text-gray-500 uppercase tracking-widest">Zero-Knowledge Verification Workflow</p>
                </div>
            </div>

            <div className="relative flex flex-col items-center gap-12 py-4">
                {/* Root Node */}
                <VisualNode
                    label="Merkle Root"
                    value={root}
                    type="root"
                    isHighlighted={isVerified}
                />

                {/* Path Nodes (Simplified for Visual Clarity) */}
                <div className="flex flex-col items-center gap-8 w-full max-w-xs relative">
                    <div className="absolute top-0 bottom-0 left-1/2 -translate-x-1/2 w-px bg-gradient-to-b from-silver-primary/50 to-transparent -z-10" />

                    {path.map((step, i) => (
                        <div key={i} className="flex items-center justify-between w-full relative">
                            <BinaryLink direction={step.direction} />
                            <VisualNode
                                label={`Layer ${path.length - i}`}
                                value={step.value}
                                type="intermediate"
                                isHighlighted={isVerified}
                            />
                        </div>
                    ))}
                </div>

                {/* Leaf Node */}
                <div className="relative">
                    <div className="absolute -top-12 left-1/2 -translate-x-1/2 h-12 w-px bg-silver-primary/30" />
                    <VisualNode
                        label="Your Leaf"
                        value={leaf}
                        type="leaf"
                        isHighlighted={isVerified}
                    />
                </div>
            </div>

            {isVerified && (
                <motion.div
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    className="mt-8 pt-4 border-t border-white/5 flex items-center justify-center gap-2"
                >
                    <Shield className="w-4 h-4 text-green-400" />
                    <span className="text-xs text-green-400 font-medium">Cryptographic Proof Path Validated</span>
                </motion.div>
            )}
        </div>
    );
};

const VisualNode = ({ label, value, type, isHighlighted }: {
    label: string,
    value: string | number,
    type: 'root' | 'leaf' | 'intermediate',
    isHighlighted: boolean
}) => {
    const [isInspecting, setIsInspecting] = React.useState(false);
    const valueStr = value.toString();
    const truncatedS = valueStr.length > 20 ? `${valueStr.slice(0, 10)}...${valueStr.slice(-8)}` : valueStr;

    return (
        <div className="relative group">
            <motion.div
                initial={{ scale: 0.9, opacity: 0 }}
                animate={{ scale: 1, opacity: 1 }}
                onClick={() => setIsInspecting(!isInspecting)}
                className={`
                    relative px-4 py-2 rounded-xl border backdrop-blur-md transition-all duration-700 cursor-pointer
                    ${isHighlighted ? 'border-silver-primary shadow-[0_0_20px_rgba(192,192,192,0.15)] bg-white/10' : 'border-white/10 bg-white/5 hover:border-white/30'}
                    ${type === 'root' ? 'scale-110 mb-2 border-dashed' : ''}
                `}
            >
                <p className="text-[8px] uppercase tracking-widest text-gray-500 mb-1 text-center font-bold">{label}</p>
                <p className="text-[10px] font-mono text-silver-primary text-center truncate">{truncatedS}</p>

                {isHighlighted && (
                    <motion.div
                        layoutId="pulse"
                        className="absolute inset-0 border border-silver-primary rounded-xl"
                        animate={{ opacity: [0.1, 0.4, 0.1], scale: [1, 1.05, 1] }}
                        transition={{ repeat: Infinity, duration: 2 }}
                    />
                )}
            </motion.div>

            <AnimatePresence>
                {isInspecting && (
                    <motion.div
                        initial={{ opacity: 0, y: 10, scale: 0.95 }}
                        animate={{ opacity: 1, y: 0, scale: 1 }}
                        exit={{ opacity: 0, y: 10, scale: 0.95 }}
                        className="absolute left-1/2 -translate-x-1/2 top-full mt-3 z-50 glass-card metallic-border p-4 min-w-[280px] shadow-3xl"
                    >
                        <div className="flex items-center justify-between mb-3 border-b border-white/5 pb-2">
                            <span className="text-[9px] font-black uppercase tracking-widest text-silver-primary">Protocol Node Inspector</span>
                            <Binary className="w-3 h-3 text-silver-primary" />
                        </div>
                        <div className="space-y-3">
                            <div>
                                <p className="text-[8px] uppercase text-gray-500 font-bold mb-1">Raw State Hash (Poseidon)</p>
                                <p className="text-[10px] font-mono text-white break-all leading-relaxed bg-black/40 p-2 rounded-lg border border-white/5">
                                    {valueStr}
                                </p>
                            </div>
                            <div className="flex gap-2">
                                <span className="px-2 py-0.5 rounded-full bg-silver-primary/10 text-silver-primary text-[8px] font-black uppercase tracking-widest">UTXO_COMMIT</span>
                                <span className="px-2 py-0.5 rounded-full bg-white/5 text-gray-500 text-[8px] font-black uppercase tracking-widest">LAYER_{type.toUpperCase()}</span>
                            </div>
                        </div>
                    </motion.div>
                )}
            </AnimatePresence>
        </div>
    );
};

const BinaryLink = ({ direction }: { direction: boolean }) => (
    <div className={`absolute ${direction ? 'right-full mr-4' : 'left-full ml-4'} flex items-center gap-2`}>
        <div className="w-8 h-px bg-white/10" />
        <div className={`p-1.5 rounded-md border border-white/5 bg-white/2 ${direction ? 'bg-silver-primary/5 text-silver-primary' : 'text-gray-600'}`}>
            <Share2 className="w-3 h-3" />
        </div>
    </div>
);
