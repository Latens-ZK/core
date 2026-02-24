"use client";

import React from 'react';

interface ErrorBoundaryState {
    hasError: boolean;
    error?: Error;
}

export class ErrorBoundary extends React.Component<
    { children: React.ReactNode; fallback?: React.ReactNode },
    ErrorBoundaryState
> {
    constructor(props: any) {
        super(props);
        this.state = { hasError: false };
    }

    static getDerivedStateFromError(error: Error): ErrorBoundaryState {
        return { hasError: true, error };
    }

    componentDidCatch(error: Error, info: React.ErrorInfo) {
        console.error("ErrorBoundary caught:", error, info);
    }

    render() {
        if (this.state.hasError) {
            return this.props.fallback ?? (
                <div className="bg-red-500/10 border border-red-500/30 rounded-2xl p-8 text-center max-w-xl mx-auto mt-10">
                    <p className="text-red-400 text-sm font-mono mb-2">ZK Environment Error</p>
                    <p className="text-gray-400 text-sm">{this.state.error?.message}</p>
                    <button
                        className="mt-4 text-xs text-gray-500 hover:text-gray-300 transition-colors"
                        onClick={() => this.setState({ hasError: false })}
                    >
                        Try again
                    </button>
                </div>
            );
        }
        return this.props.children;
    }
}
