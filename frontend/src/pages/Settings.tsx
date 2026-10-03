import React from 'react';
import { useAuth } from '../context/AuthContext';
import { useTheme } from '../context/ThemeContext';
import { Card } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';
import {
  User as UserIcon,
  Shield,
  Sun,
  Moon,
  Monitor,
  Server,
  KeyRound,
  CheckCircle2,
  Lock,
} from 'lucide-react';

export const Settings: React.FC = () => {
  const { user, role } = useAuth();
  const { theme, setTheme } = useTheme();

  const roleVariant = role === 'ADMIN' ? 'cyan' : role === 'USER' ? 'green' : 'slate';

  return (
    <div className="space-y-6 max-w-4xl">
      {/* Header Banner */}
      <div className="p-6 bg-slate-900/60 border border-slate-800/80 rounded-2xl">
        <h2 className="text-xl font-bold text-slate-100 flex items-center gap-2">
          <UserIcon className="w-5 h-5 text-cyan-400" />
          <span>Settings & Profile</span>
        </h2>
        <p className="text-xs text-slate-400 mt-1">
          Manage your user profile, interface theme preferences, and review system configuration.
        </p>
      </div>

      {/* Profile Section */}
      <Card className="space-y-4">
        <div className="flex items-center gap-2 border-b border-slate-800 pb-3">
          <UserIcon className="w-4 h-4 text-cyan-400" />
          <h3 className="text-sm font-bold text-slate-100">User Profile</h3>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-xs font-mono">
          <div className="p-3 bg-slate-950 border border-slate-800 rounded-xl space-y-1">
            <span className="text-slate-500 block">Username</span>
            <span className="text-sm font-bold text-slate-100">{user?.username || 'admin'}</span>
          </div>

          <div className="p-3 bg-slate-950 border border-slate-800 rounded-xl space-y-1">
            <span className="text-slate-500 block">Role</span>
            <div className="pt-0.5">
              <Badge variant={roleVariant} size="md" icon={<Shield className="w-3 h-3" />}>
                {role}
              </Badge>
            </div>
          </div>

          <div className="p-3 bg-slate-950 border border-slate-800 rounded-xl space-y-1">
            <span className="text-slate-500 block">User ID</span>
            <span className="text-[11px] text-slate-300 truncate block">{user?.id || 'N/A'}</span>
          </div>
        </div>
      </Card>

      {/* Appearance Section */}
      <Card className="space-y-4">
        <div className="flex items-center gap-2 border-b border-slate-800 pb-3">
          <Moon className="w-4 h-4 text-cyan-400" />
          <h3 className="text-sm font-bold text-slate-100">Appearance & Theme</h3>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <button
            onClick={() => setTheme('dark')}
            className={`p-4 rounded-xl border flex items-center gap-3 transition-all ${
              theme === 'dark'
                ? 'bg-cyan-500/10 border-cyan-500/50 text-cyan-400 font-bold'
                : 'bg-slate-950 border-slate-800 text-slate-400 hover:text-slate-200'
            }`}
          >
            <Moon className="w-5 h-5" />
            <div className="text-left text-xs">
              <span className="block font-semibold">Dark Mode</span>
              <span className="text-[10px] text-slate-500">Sleek dark theme</span>
            </div>
          </button>

          <button
            onClick={() => setTheme('light')}
            className={`p-4 rounded-xl border flex items-center gap-3 transition-all ${
              theme === 'light'
                ? 'bg-cyan-500/10 border-cyan-500/50 text-cyan-400 font-bold'
                : 'bg-slate-950 border-slate-800 text-slate-400 hover:text-slate-200'
            }`}
          >
            <Sun className="w-5 h-5" />
            <div className="text-left text-xs">
              <span className="block font-semibold">Light Mode</span>
              <span className="text-[10px] text-slate-500">Bright clean theme</span>
            </div>
          </button>

          <button
            onClick={() => setTheme('system')}
            className={`p-4 rounded-xl border flex items-center gap-3 transition-all ${
              theme === 'system'
                ? 'bg-cyan-500/10 border-cyan-500/50 text-cyan-400 font-bold'
                : 'bg-slate-950 border-slate-800 text-slate-400 hover:text-slate-200'
            }`}
          >
            <Monitor className="w-5 h-5" />
            <div className="text-left text-xs">
              <span className="block font-semibold">System Default</span>
              <span className="text-[10px] text-slate-500">Sync with OS setting</span>
            </div>
          </button>
        </div>
      </Card>

      {/* System & API Information Section */}
      <Card className="space-y-4">
        <div className="flex items-center gap-2 border-b border-slate-800 pb-3">
          <Server className="w-4 h-4 text-cyan-400" />
          <h3 className="text-sm font-bold text-slate-100">System & Environment Info</h3>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs font-mono">
          <div className="p-3 bg-slate-950 border border-slate-800 rounded-xl space-y-1">
            <span className="text-slate-500 block">API Base URL</span>
            <span className="text-slate-200 font-bold">{import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'}</span>
          </div>

          <div className="p-3 bg-slate-950 border border-slate-800 rounded-xl space-y-1">
            <span className="text-slate-500 block">Application Version</span>
            <span className="text-slate-200 font-bold">1.0.0 (Production Build)</span>
          </div>
        </div>

        {/* Security Notice Box */}
        <div className="p-4 bg-slate-950/80 border border-slate-800 rounded-xl flex items-start gap-3 text-xs text-slate-400">
          <Lock className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
          <div>
            <span className="font-semibold text-slate-200 block mb-0.5">Security & Privacy Guarantee</span>
            <span>
              All JWT tokens are securely held in isolated client storage and sent strictly via Bearer headers. No secret keys or backend credentials are exposed to the browser.
            </span>
          </div>
        </div>
      </Card>
    </div>
  );
};
