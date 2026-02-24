"use client";

import React, { useEffect, useRef } from 'react';

export const BackgroundEffect = () => {
    const canvasRef = useRef<HTMLCanvasElement>(null);

    useEffect(() => {
        const canvas = canvasRef.current;
        if (!canvas) return;

        const ctx = canvas.getContext('2d');
        if (!ctx) return;

        let width = window.innerWidth;
        let height = window.innerHeight;
        canvas.width = width;
        canvas.height = height;

        const particles: { x: number; y: number; speed: number; opacity: number }[] = [];
        const particleCount = 100;

        for (let i = 0; i < particleCount; i++) {
            particles.push({
                x: Math.random() * width,
                y: Math.random() * height,
                speed: 0.5 + Math.random() * 1.5,
                opacity: Math.random() * 0.5
            });
        }

        const animate = () => {
            ctx.clearRect(0, 0, width, height);

            // Draw grid
            ctx.strokeStyle = 'rgba(200, 200, 200, 0.04)'; // Subtle silver grid
            ctx.lineWidth = 0.5;
            const gridSize = 60;

            for (let x = 0; x < width; x += gridSize) {
                ctx.beginPath();
                ctx.moveTo(x, 0);
                ctx.lineTo(x, height);
                ctx.stroke();
            }

            for (let y = 0; y < height; y += gridSize) {
                ctx.beginPath();
                ctx.moveTo(0, y);
                ctx.lineTo(width, y);
                ctx.stroke();
            }

            // Draw particles
            ctx.fillStyle = '#ffffff'; // White/Silver particles
            particles.forEach(p => {
                p.y -= p.speed * 0.5; // Slower, more elegant movement
                if (p.y < 0) {
                    p.y = height;
                    p.x = Math.random() * width;
                }

                ctx.globalAlpha = p.opacity * 0.4;
                ctx.beginPath();
                ctx.arc(p.x, p.y, 1, 0, Math.PI * 2);
                ctx.fill();
                ctx.globalAlpha = 1;
            });

            requestAnimationFrame(animate);
        };

        animate();

        const handleResize = () => {
            width = window.innerWidth;
            height = window.innerHeight;
            canvas.width = width;
            canvas.height = height;
        };

        window.addEventListener('resize', handleResize);
        return () => window.removeEventListener('resize', handleResize);
    }, []);

    return (
        <canvas
            ref={canvasRef}
            className="fixed top-0 left-0 w-full h-full -z-10 pointer-events-none bg-black"
        />
    );
};
