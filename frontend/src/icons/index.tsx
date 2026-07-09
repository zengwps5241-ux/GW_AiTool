// Lucide 风格线形图标库:stroke 1.6,currentColor
// TS 移植自 ui-refer/ai-ops/icons.jsx
import type { CSSProperties, ReactNode, SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement> & {
  size?: number;
  sw?: number;
};

interface BaseProps extends IconProps {
  d?: string;
  children?: ReactNode;
}

const Base = ({ d, size = 18, sw = 1.6, children, ...props }: BaseProps) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth={sw}
    strokeLinecap="round"
    strokeLinejoin="round"
    {...props}
  >
    {d ? <path d={d} /> : children}
  </svg>
);

export const I = {
  Logo: ({ size = 24, style }: { size?: number; style?: CSSProperties }) => (
    <img
      src="/logo.png"
      alt="logo"
      width={size}
      height={size}
      style={{ display: "block", ...style }}
    />
  ),
  Plus: (p: IconProps) => <Base {...p} d="M12 5v14M5 12h14" />,
  Minus: (p: IconProps) => <Base {...p} d="M5 12h14" />,
  Search: (p: IconProps) => (
    <Base {...p}>
      <circle cx="11" cy="11" r="7" />
      <path d="m20 20-3.5-3.5" />
    </Base>
  ),
  ChevronDown: (p: IconProps) => <Base {...p} d="m6 9 6 6 6-6" />,
  ChevronRight: (p: IconProps) => <Base {...p} d="m9 6 6 6-6 6" />,
  ChevronLeft: (p: IconProps) => <Base {...p} d="m15 6-6 6 6 6" />,
  ChevronUp: (p: IconProps) => <Base {...p} d="m6 15 6-6 6 6" />,
  More: (p: IconProps) => (
    <Base {...p}>
      <circle cx="5" cy="12" r="1" />
      <circle cx="12" cy="12" r="1" />
      <circle cx="19" cy="12" r="1" />
    </Base>
  ),
  Send: (p: IconProps) => <Base {...p} d="m22 2-7 20-4-9-9-4 20-7Z" />,
  Stop: (p: IconProps) => (
    <Base {...p}>
      <rect x="6" y="6" width="12" height="12" rx="1.5" />
    </Base>
  ),
  Paperclip: (p: IconProps) => (
    <Base
      {...p}
      d="m21 12-9.5 9.5a5 5 0 0 1-7-7L14 5a3.5 3.5 0 1 1 5 5l-9.5 9.5a2 2 0 0 1-3-3L16 7"
    />
  ),
  User: (p: IconProps) => (
    <Base {...p}>
      <circle cx="12" cy="8" r="4" />
      <path d="M4 21a8 8 0 0 1 16 0" />
    </Base>
  ),
  Lock: (p: IconProps) => (
    <Base {...p}>
      <rect x="4" y="11" width="16" height="10" rx="2" />
      <path d="M8 11V7a4 4 0 0 1 8 0v4" />
    </Base>
  ),
  Eye: (p: IconProps) => (
    <Base {...p}>
      <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7Z" />
      <circle cx="12" cy="12" r="3" />
    </Base>
  ),
  EyeOff: (p: IconProps) => (
    <Base
      {...p}
      d="m3 3 18 18M10.6 10.6a2 2 0 0 0 2.8 2.8M9.4 5.5A10.6 10.6 0 0 1 12 5c6.5 0 10 7 10 7a17.4 17.4 0 0 1-3.7 4.5M6.6 6.6A17.4 17.4 0 0 0 2 12s3.5 7 10 7c1.7 0 3.2-.4 4.6-1"
    />
  ),
  Check: (p: IconProps) => <Base {...p} d="m5 12 5 5L20 7" />,
  X: (p: IconProps) => <Base {...p} d="M6 6l12 12M18 6 6 18" />,
  AlertTriangle: (p: IconProps) => (
    <Base {...p}>
      <path d="M12 3 2 21h20L12 3Z" />
      <path d="M12 9v5" />
      <circle cx="12" cy="17.5" r=".6" fill="currentColor" />
    </Base>
  ),
  Shield: (p: IconProps) => (
    <Base {...p} d="M12 3 4 6v6c0 5 3.5 8 8 9 4.5-1 8-4 8-9V6l-8-3Z" />
  ),
  Wrench: (p: IconProps) => (
    <Base
      {...p}
      d="M14.7 6.3a4 4 0 0 0 5 5L21 13l-8 8-3-3 8-8-1.3-1.3a4 4 0 0 0-5-5L9 5l3 3-3 3-3-3 1.3-1.3a4 4 0 0 1 5-5Z"
    />
  ),
  Server: (p: IconProps) => (
    <Base {...p}>
      <rect x="3" y="4" width="18" height="7" rx="1.5" />
      <rect x="3" y="13" width="18" height="7" rx="1.5" />
      <circle cx="7" cy="7.5" r=".6" fill="currentColor" />
      <circle cx="7" cy="16.5" r=".6" fill="currentColor" />
    </Base>
  ),
  Activity: (p: IconProps) => <Base {...p} d="M3 12h4l3-8 4 16 3-8h4" />,
  ClipboardCheck: (p: IconProps) => (
    <Base {...p}>
      <rect x="6" y="4" width="12" height="17" rx="2" />
      <path d="M9 4V3a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v1" />
      <path d="m9 13 2 2 4-4" />
    </Base>
  ),
  Database: (p: IconProps) => (
    <Base {...p}>
      <ellipse cx="12" cy="5" rx="8" ry="3" />
      <path d="M4 5v6c0 1.7 3.6 3 8 3s8-1.3 8-3V5" />
      <path d="M4 11v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6" />
    </Base>
  ),
  Bell: (p: IconProps) => (
    <Base {...p}>
      <path d="M6 8a6 6 0 0 1 12 0c0 6 3 7 3 7H3s3-1 3-7Z" />
      <path d="M10 21a2 2 0 0 0 4 0" />
    </Base>
  ),
  MessageSquare: (p: IconProps) => (
    <Base {...p}>
      <path d="M21 15a4 4 0 0 1-4 4H8l-5 3V7a4 4 0 0 1 4-4h10a4 4 0 0 1 4 4v8Z" />
    </Base>
  ),
  MessagesSquare: (p: IconProps) => (
    <Base {...p}>
      <path d="M14 9a2 2 0 0 1-2 2H6l-4 4V4c0-1.1.9-2 2-2h8a2 2 0 0 1 2 2v5Z" />
      <path d="M18 9h2a2 2 0 0 1 2 2v11l-4-4h-6a2 2 0 0 1-2-2v-1" />
    </Base>
  ),
  Settings: (p: IconProps) => (
    <Base {...p}>
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3h.1a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8v.1a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1Z" />
    </Base>
  ),
  LayoutDashboard: (p: IconProps) => (
    <Base {...p}>
      <rect x="3" y="3" width="8" height="10" rx="1.5" />
      <rect x="13" y="3" width="8" height="6" rx="1.5" />
      <rect x="13" y="11" width="8" height="10" rx="1.5" />
      <rect x="3" y="15" width="8" height="6" rx="1.5" />
    </Base>
  ),
  Users: (p: IconProps) => (
    <Base {...p}>
      <circle cx="9" cy="8" r="3.5" />
      <path d="M2 21a7 7 0 0 1 14 0" />
      <path d="M16 4a3.5 3.5 0 0 1 0 7" />
      <path d="M22 21a7 7 0 0 0-5-6.7" />
    </Base>
  ),
  PanelLeft: (p: IconProps) => (
    <Base {...p}>
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <path d="M9 4v16" />
    </Base>
  ),
  Sun: (p: IconProps) => (
    <Base {...p}>
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
    </Base>
  ),
  Moon: (p: IconProps) => <Base {...p} d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8Z" />,
  Copy: (p: IconProps) => (
    <Base {...p}>
      <rect x="8" y="8" width="12" height="12" rx="2" />
      <path d="M4 16V6a2 2 0 0 1 2-2h10" />
    </Base>
  ),
  Refresh: (p: IconProps) => (
    <Base
      {...p}
      d="M3 12a9 9 0 0 1 15-6.7L21 8M21 3v5h-5M21 12a9 9 0 0 1-15 6.7L3 16M3 21v-5h5"
    />
  ),
  Upload: (p: IconProps) => (
    <Base {...p} d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12" />
  ),
  Sparkles: (p: IconProps) => (
    <Base
      {...p}
      d="M12 3v4M12 17v4M3 12h4M17 12h4M5.6 5.6l2.8 2.8M15.6 15.6l2.8 2.8M5.6 18.4l2.8-2.8M15.6 8.4l2.8-2.8"
    />
  ),
  // 插头:用于标识可选的本地插件
  Plug: (p: IconProps) => (
    <Base {...p}>
      <path d="M9 2v6M15 2v6M7 8h10v3a5 5 0 0 1-10 0V8zM12 16v4" />
    </Base>
  ),
  Terminal: (p: IconProps) => (
    <Base {...p}>
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <path d="m7 9 3 3-3 3M13 15h4" />
    </Base>
  ),
  CircleCheck: (p: IconProps) => (
    <Base {...p}>
      <circle cx="12" cy="12" r="9" />
      <path d="m8 12 3 3 5-6" />
    </Base>
  ),
  CircleX: (p: IconProps) => (
    <Base {...p}>
      <circle cx="12" cy="12" r="9" />
      <path d="m9 9 6 6M15 9l-6 6" />
    </Base>
  ),
  CircleAlert: (p: IconProps) => (
    <Base {...p}>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v6" />
      <circle cx="12" cy="16.5" r=".6" fill="currentColor" />
    </Base>
  ),
  CircleDot: (p: IconProps) => (
    <Base {...p}>
      <circle cx="12" cy="12" r="9" />
      <circle cx="12" cy="12" r="3" fill="currentColor" />
    </Base>
  ),
  Loader: (p: IconProps) => (
    <Base
      {...p}
      d="M21 12a9 9 0 1 1-6.3-8.6"
      style={{ animation: "spin 0.9s linear infinite" }}
    />
  ),
  Power: (p: IconProps) => <Base {...p} d="M12 3v9M5.6 7.6a8 8 0 1 0 12.8 0" />,
  Edit: (p: IconProps) => <Base {...p} d="M4 20h4l11-11-4-4L4 16v4Zm10-14 4 4" />,
  Download: (p: IconProps) => (
    <Base {...p}>
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
      <path d="m7 10 5 5 5-5" />
      <path d="M12 15V3" />
    </Base>
  ),
  Maximize: (p: IconProps) => (
    <Base {...p}>
      <path d="M8 3H3v5M16 3h5v5M21 16v5h-5M3 16v5h5" />
    </Base>
  ),
  ExternalLink: (p: IconProps) => (
    <Base {...p}>
      <path d="M15 3h6v6" />
      <path d="M10 14 21 3" />
      <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
    </Base>
  ),
  Trash: (p: IconProps) => (
    <Base
      {...p}
      d="M3 6h18M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2M6 6v14a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2V6M10 11v6M14 11v6"
    />
  ),
  Brain: (p: IconProps) => (
    <Base
      {...p}
      d="M9.5 4a3 3 0 0 0-3 3v.2A3 3 0 0 0 4 10v1a3 3 0 0 0 .5 4 3 3 0 0 0 5 4 3 3 0 0 0 5 0 3 3 0 0 0 5-4 3 3 0 0 0 .5-4v-1a3 3 0 0 0-2.5-2.8V7a3 3 0 0 0-3-3 3 3 0 0 0-2.5 1.5A3 3 0 0 0 9.5 4Z"
    />
  ),
  LogOut: (p: IconProps) => (
    <Base {...p}>
      <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
      <path d="m16 17 5-5-5-5M21 12H9" />
    </Base>
  ),
  Folder: (p: IconProps) => (
    <Base
      {...p}
      d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Z"
    />
  ),
  FolderOpen: (p: IconProps) => (
    <Base {...p}>
      <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v1" />
      <path d="M3 9h17l-2 8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V9Z" />
    </Base>
  ),
  File: (p: IconProps) => (
    <Base {...p}>
      <path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9l-6-6Z" />
      <path d="M14 3v6h6" />
    </Base>
  ),
  // 多文件夹:用于表示团队空间这类共享文件夹集合
  Folders: (p: IconProps) => (
    <Base {...p}>
      <path d="M7 6a2 2 0 0 1 2-2h3l2 2h5a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-2" />
      <path d="M3 10a2 2 0 0 1 2-2h3l2 2h5a2 2 0 0 1 2 2v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-8Z" />
    </Base>
  ),
  Puzzle: (p: IconProps) => (
    <Base {...p}>
      <path d="M15.5 7.5A2.5 2.5 0 0 0 13 5H7a2 2 0 0 0-2 2v5a2 2 0 0 0 2 2h1.5a2.5 2.5 0 0 1 0 5H7a2 2 0 0 0-2 2v2a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-5a2 2 0 0 0-2-2h-1.5a2.5 2.5 0 0 1 0-5H13a2 2 0 0 0 2-2V7.5Z" />
    </Base>
  ),
  // 筛选漏斗图标
  Filter: (p: IconProps) => (
    <Base {...p}>
      <path d="M22 3H2l8 9.46V19l4 2v-8.54L22 3Z" />
    </Base>
  ),
  // 地图图标:用于业务地图导航
  Map: (p: IconProps) => (
    <Base {...p}>
      <path d="M3 7L9 4L15 7L21 4V17L15 20L9 17L3 20V7Z" />
      <path d="M9 4V17" />
      <path d="M15 7V20" />
    </Base>
  ),
  // 靶心图标:用于营销地图导航
  Target: (p: IconProps) => (
    <Base {...p}>
      <circle cx="12" cy="12" r="9" />
      <circle cx="12" cy="12" r="5" />
      <circle cx="12" cy="12" r="1" fill="currentColor" />
    </Base>
  ),
  // 剪贴板列表图标:用于拜访记录导航
  ClipboardList: (p: IconProps) => (
    <Base {...p}>
      <rect x="6" y="4" width="12" height="17" rx="2" />
      <path d="M9 4V3a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v1" />
      <path d="M9 11h6" />
      <path d="M9 15h6" />
      <path d="M9 8h6" />
    </Base>
  ),
  // 项目切换图标:用于项目选择器
  Briefcase: (p: IconProps) => (
    <Base {...p}>
      <rect x="3" y="7" width="18" height="13" rx="2" />
      <path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
    </Base>
  ),
  // 用户勾选图标:用于用户审批
  UserCheck: (p: IconProps) => (
    <Base {...p}>
      <circle cx="9" cy="8" r="3.5" />
      <path d="M2 21a7 7 0 0 1 14 0" />
      <path d="m15 8 3 3 5-6" />
    </Base>
  ),
  // 建筑图标:用于组织架构
  Building: (p: IconProps) => (
    <Base {...p}>
      <rect x="3" y="3" width="18" height="18" rx="2" />
      <path d="M9 3v18M15 3v18M3 9h18M3 15h18" />
    </Base>
  ),
};

export default I;
