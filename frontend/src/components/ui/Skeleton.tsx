import React from 'react';

export const Skeleton: React.FC<{ className?: string }> = ({ className = '' }) => (
  <div className={`bg-slate-800/60 animate-pulse rounded-lg ${className}`} />
);

export const SkeletonCard: React.FC = () => (
  <div className="bg-slate-900/50 border border-slate-800 p-5 rounded-2xl space-y-3">
    <Skeleton className="h-4 w-1/3" />
    <Skeleton className="h-8 w-1/2" />
    <Skeleton className="h-3 w-3/4" />
  </div>
);

export const SkeletonTable: React.FC<{ rows?: number }> = ({ rows = 5 }) => (
  <div className="w-full space-y-3">
    {Array.from({ length: rows }).map((_, i) => (
      <div key={i} className="flex items-center gap-4 p-4 bg-slate-900/40 border border-slate-800/60 rounded-xl">
        <Skeleton className="h-5 w-5 rounded" />
        <Skeleton className="h-4 w-1/4" />
        <Skeleton className="h-4 w-1/3" />
        <Skeleton className="h-4 w-1/6 ml-auto" />
      </div>
    ))}
  </div>
);
