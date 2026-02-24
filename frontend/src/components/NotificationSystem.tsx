"use client";

import React, { createContext, useContext, useState, useCallback, ReactNode } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, CheckCircle, AlertCircle, Info, Bell } from 'lucide-react';

type NotificationType = 'success' | 'error' | 'info';

interface Notification {
    id: string;
    message: string;
    type: NotificationType;
}

interface NotificationContextType {
    notify: (message: string, type?: NotificationType) => void;
}

const NotificationContext = createContext<NotificationContextType | undefined>(undefined);

export const NotificationProvider = ({ children }: { children: ReactNode }) => {
    const [notifications, setNotifications] = useState<Notification[]>([]);

    const notify = useCallback((message: string, type: NotificationType = 'info') => {
        const id = Math.random().toString(36).substring(2, 9);
        setNotifications(prev => [...prev, { id, message, type }]);
        setTimeout(() => {
            setNotifications(prev => prev.filter(n => n.id !== id));
        }, 5000);
    }, []);

    const remove = (id: string) => {
        setNotifications(prev => prev.filter(n => n.id !== id));
    };

    return (
        <NotificationContext.Provider value={{ notify }}>
            {children}
            <div className="fixed bottom-6 right-6 z-[100] flex flex-col gap-3 pointer-events-none">
                <AnimatePresence>
                    {notifications.map(n => (
                        <motion.div
                            key={n.id}
                            initial={{ opacity: 0, x: 20, scale: 0.9 }}
                            animate={{ opacity: 1, x: 0, scale: 1 }}
                            exit={{ opacity: 0, x: 20, scale: 0.9 }}
                            className="pointer-events-auto"
                        >
                            <div className={`
                                glass-card px-5 py-4 min-w-[300px] flex items-center gap-4 shadow-2xl border-l-4
                                ${n.type === 'success' ? 'border-l-silver-primary' : n.type === 'error' ? 'border-l-red-500' : 'border-l-gray-500'}
                            `}>
                                <div className={`
                                    p-2 rounded-lg 
                                    ${n.type === 'success' ? 'bg-silver-primary/10 text-silver-primary' : n.type === 'error' ? 'bg-red-500/10 text-red-400' : 'bg-white/5 text-gray-400'}
                                `}>
                                    {n.type === 'success' && <CheckCircle className="w-5 h-5" />}
                                    {n.type === 'error' && <AlertCircle className="w-5 h-5" />}
                                    {n.type === 'info' && <Bell className="w-5 h-5" />}
                                </div>
                                <div className="flex-grow pr-4">
                                    <p className="text-xs font-bold uppercase tracking-widest text-white">{n.type === 'info' ? 'Update' : n.type}</p>
                                    <p className="text-[10px] text-gray-400 font-medium leading-relaxed">{n.message}</p>
                                </div>
                                <button
                                    onClick={() => remove(n.id)}
                                    className="p-1 hover:bg-white/5 rounded-md transition-colors"
                                >
                                    <X className="w-4 h-4 text-gray-600" />
                                </button>
                            </div>
                        </motion.div>
                    ))}
                </AnimatePresence>
            </div>
        </NotificationContext.Provider>
    );
};

export const useNotify = () => {
    const context = useContext(NotificationContext);
    if (!context) throw new Error('useNotify must be used within NotificationProvider');
    return context;
};
