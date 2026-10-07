import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'ContractIQ — Understand Any Property Contract Instantly',
  description: 'Upload any terms & conditions, lease agreement, or property contract and ask questions in plain English. AI-powered contract analysis for real estate.',
  keywords: ['contract analyzer', 'real estate AI', 'lease agreement', 'property contract', 'legal document analysis'],
  openGraph: {
    title: 'ContractIQ — Smart Contract Analysis',
    description: 'Understand any property contract in plain English with AI',
    type: 'website',
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Outfit:wght@700;800;900&display=swap"
          rel="stylesheet"
        />
      </head>
      <body style={{ fontFamily: "'Inter', sans-serif", margin: 0 }}>
        {children}
      </body>
    </html>
  );
}
