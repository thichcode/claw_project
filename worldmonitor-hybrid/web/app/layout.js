import "./globals.css";

export const metadata = {
  title: "WorldMonitor",
  description: "Hybrid monitoring dashboard",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>
        <div className="wm-shell">
          <nav className="wm-nav">
            <a href="/">Dashboard</a>
            <a href="/alerts">Alerts</a>
            <a href="/incidents">Incidents</a>
            <a href="/executive">Executive</a>
            <a href="/topology">Topology</a>
            <a href="/rca">RCA</a>
          </nav>
          {children}
        </div>
      </body>
    </html>
  );
}
