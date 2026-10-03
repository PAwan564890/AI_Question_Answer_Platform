import React from 'react';

interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  children: React.ReactNode;
  className?: string;
  hoverable?: boolean;
}

export const Card: React.FC<CardProps> = ({
  children,
  className = '',
  hoverable = false,
  ...props
}) => {
  return (
    <div
      className={`bg-slate-900/60 border border-slate-800/80 rounded-2xl p-5 backdrop-blur-sm ${
        hoverable ? 'hover:border-slate-700/80 transition-all duration-200 hover:shadow-lg hover:shadow-cyan-950/20' : ''
      } ${className}`}
      {...props}
    >
      {children}
    </div>
  );
};
