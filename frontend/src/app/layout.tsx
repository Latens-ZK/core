import type { Metadata } from 'next'
import { Inter } from 'next/font/google'
import { NotificationProvider } from '../components/NotificationSystem'

const inter = Inter({ subsets: ['latin'] })

export const metadata: Metadata = {
    title: 'Latens - Zero-Knowledge Bitcoin Verification',
    description: 'Verify Bitcoin state on Starknet without revealing your address',
}

export default function RootLayout({
    children,
}: {
    children: React.ReactNode
}) {
    return (
        <html lang="en">
            <body className={inter.className}>
                <NotificationProvider>
                    {children}
                </NotificationProvider>
            </body>
        </html>
    )
}
