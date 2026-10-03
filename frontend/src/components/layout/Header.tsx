import React, { useState, useEffect, useRef } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { useTheme } from '../../context/ThemeContext';
import { opsApi } from '../../api/ops';
import {
  Menu,
  Sun,
  Moon,
  Search,
  User as UserIcon,
  LogOut,
  Settings as SettingsIcon,
  ChevronDown,
  Activity,
} from 'lucide-react';
import { Badge } from '../ui/Badge';

interface HeaderProps {
  onMobileMenuClick: () => void;
}

const pageTitles: Record<string, string> = {
  '/dashboard': 'Dashboard',
  '/chat': 'AI Assistant Chat',
  '/knowledge-base': 'Knowledge Base',
  '/search': 'Vector Search',
  '/history': 'Chat History',
  '/users': 'User Management',
  '/audit': 'Audit Logs',
  '/health': 'System Health',
  '/metrics': 'System Metrics',
  '/settings': 'Settings & Profile',
};

export const Header: React.FC<HeaderProps> = ({ onMobileMenuClick }) => {
  const { user, role, logout } = useAuth();
  const { theme, setTheme, isDark } = useTheme();
  const location = useLocation();
  const navigate = useNavigate();

  const [dropdownOpen, setDropdownOpen] = useState<boolean>(false);
  const [healthStatus, setHealthStatus] = useState<'ok' | 'degraded' | 'unhealthy' | 'loading'>('loading');
  const dropdownRef = useRef<HTMLDivElement>(null);

  const title = pageTitles[location.pathname] || 'AI Platform';

  useEffect(() => {
    const fetchHealth = async () => {
      try {
        const res = await opsApi.getHealth();
        setHealthStatus(res.status);
      } catch {
        setHealthStatus('unhealthy');
      }
    };
    fetchHealth();
    const interval = setInterval(fetchHealth, 30000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setDropdownOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const statusColors = {
    ok: 'bg-emerald-500 text-emerald-400',
    degraded: 'bg-amber-500 text-amber-400',
    unhealthy: 'bg-rose-500 text-rose-400',
    loading: 'bg-slate-500 text-slate-400',
  };

  const statusLabels = {
    ok: 'System Operational',
    degraded: 'System Degraded',
    unhealthy: 'System Outage',
    loading: 'Checking System...',
  };

  const roleVariant = role === 'ADMIN' ? 'cyan' : role === 'USER' ? 'green' : 'slate';

  return (
    <header className="sticky top-0 z-30 h-16 bg-slate-900/80 backdrop-blur-md border-b border-slate-800/80 px-4 md:px-6 flex items-center justify-between">
      {/* Left: Mobile Menu Button & Page Title */}
      <div className="flex items-center gap-3">
        <button
          onClick={onMobileMenuClick}
          className="p-2 text-slate-400 hover:text-slate-100 bg-slate-800/60 rounded-xl md:hidden"
          aria-label="Open navigation menu"
        >
          <Menu className="w-5 h-5" />
        </button>
        <div>
          <h1 className="text-lg font-bold text-slate-100 tracking-tight">{title}</h1>
        </div>
      </div>

      {/* Right: Controls & User Profile */}
      <div className="flex items-center gap-3">
        {/* Global Search shortcut button */}
        <button
          onClick={() => navigate('/search')}
          className="hidden sm:flex items-center gap-2 px-3 py-1.5 bg-slate-800/60 hover:bg-slate-800 border border-slate-700/60 rounded-xl text-xs text-slate-400 hover:text-slate-200 transition-colors"
        >
          <Search className="w-3.5 h-3.5" />
          <span>Search KB...</span>
          <kbd className="px-1.5 py-0.5 bg-slate-900 border border-slate-700 rounded text-[10px] font-mono text-slate-400">⌘K</kbd>
        </button>

        {/* System status pill */}
        <div className="flex items-center gap-2 px-2.5 py-1 bg-slate-800/40 border border-slate-800 rounded-xl">
          <span className={`w-2 h-2 rounded-full ${statusColors[healthStatus].split(' ')[0]} animate-pulse`} />
          <span className="text-xs font-medium text-slate-300 hidden md:inline">{statusLabels[healthStatus]}</span>
        </div>

        {/* Theme Toggle */}
        <button
          onClick={() => setTheme(isDark ? 'light' : 'dark')}
          className="p-2 text-slate-400 hover:text-slate-100 bg-slate-800/60 hover:bg-slate-800 border border-slate-700/60 rounded-xl transition-colors"
          title={`Switch to ${isDark ? 'Light' : 'Dark'} mode`}
        >
          {isDark ? <Sun className="w-4 h-4 text-amber-400" /> : <Moon className="w-4 h-4 text-cyan-400" />}
        </button>

        {/* User Dropdown */}
        <div className="relative" ref={dropdownRef}>
          <button
            onClick={() => setDropdownOpen(!dropdownOpen)}
            className="flex items-center gap-2 p-1.5 hover:bg-slate-800/60 border border-transparent hover:border-slate-700/60 rounded-xl transition-colors"
          >
            <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-cyan-600/20 text-cyan-400 font-bold border border-cyan-500/30 text-xs">
              {user?.username ? user.username.substring(0, 2).toUpperCase() : <UserIcon className="w-4 h-4" />}
            </div>
            <div className="hidden sm:flex flex-col text-left">
              <span className="text-xs font-semibold text-slate-200">{user?.username}</span>
              <Badge variant={roleVariant} size="sm">{role}</Badge>
            </div>
            <ChevronDown className="w-4 h-4 text-slate-400 hidden sm:block" />
          </button>

          {dropdownOpen && (
            <div className="absolute right-0 mt-2 w-48 bg-slate-900 border border-slate-800 rounded-2xl shadow-xl py-2 z-50 animate-fade-in">
              <div className="px-4 py-2 border-b border-slate-800">
                <p className="text-xs font-semibold text-slate-200 truncate">{user?.username}</p>
                <p className="text-[10px] text-slate-400">Role: {role}</p>
              </div>
              <button
                onClick={() => {
                  setDropdownOpen(false);
                  navigate('/settings');
                }}
                className="w-full flex items-center gap-2.5 px-4 py-2 text-xs text-slate-300 hover:bg-slate-800/80 hover:text-slate-100 transition-colors"
              >
                <SettingsIcon className="w-4 h-4 text-slate-400" />
                <span>Profile & Settings</span>
              </button>
              <button
                onClick={() => {
                  setDropdownOpen(false);
                  navigate('/health');
                }}
                className="w-full flex items-center gap-2.5 px-4 py-2 text-xs text-slate-300 hover:bg-slate-800/80 hover:text-slate-100 transition-colors"
              >
                <Activity className="w-4 h-4 text-slate-400" />
                <span>System Health</span>
              </button>
              <div className="my-1 border-t border-slate-800" />
              <button
                onClick={handleLogout}
                className="w-full flex items-center gap-2.5 px-4 py-2 text-xs text-rose-400 hover:bg-rose-500/10 transition-colors"
              >
                <LogOut className="w-4 h-4" />
                <span>Log out</span>
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
};
