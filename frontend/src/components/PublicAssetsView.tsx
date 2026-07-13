import { useCallback, useEffect, useState } from "react";
import { api } from "@/api/client";
import type { PublicAssetItem, PublicAssetsOut } from "@/types";
import { Btn, Spinner, Tag } from "@/components/ui";
import { I } from "@/icons";

/**
 * 团队空间「公开资产区」（M5.5.3，§2.6 / §6.3）。
 *
 * 跨项目聚合展示：
 * - 公开资产：各数据页面标记「完全公开」的对象（is_public=true，§6.3）
 * - 共享给我的：他人「共享给」当前用户的对象（shared_with∋me，§5.x）
 *
 * 按类型分组：角色卡 / 业务地图片段 / 拜访记录。
 * 自管 fetch + 静默错误（同 Banner 范式：辅助视图失败不阻塞主流程）。
 */

const TYPE_META: Record<
  PublicAssetItem["object_type"],
  { label: string; icon: React.ReactNode; tone: "accent" | "info" | "success" }
> = {
  card: { label: "角色卡", icon: <I.User size={14} />, tone: "accent" },
  business_object: { label: "业务地图片段", icon: <I.Map size={14} />, tone: "info" },
  visit: { label: "拜访记录", icon: <I.Calendar size={14} />, tone: "success" },
};

function AssetCard({ item }: { item: PublicAssetItem }) {
  const meta = TYPE_META[item.object_type];
  return (
    <article
      style={{
        border: "1px solid var(--line)",
        borderRadius: 8,
        padding: 12,
        background: "var(--surface)",
        boxShadow: "var(--shadow-sm)",
        display: "flex",
        flexDirection: "column",
        gap: 6,
        minHeight: 110,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 0 }}>
        <span
          style={{
            width: 26,
            height: 26,
            borderRadius: 6,
            background: "var(--bg-2)",
            color: "var(--ink-2)",
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            flexShrink: 0,
          }}
        >
          {meta.icon}
        </span>
        <div
          style={{
            fontSize: 14,
            fontWeight: 600,
            color: "var(--ink)",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
            flex: 1,
            minWidth: 0,
          }}
          title={item.title}
        >
          {item.title}
        </div>
        <Tag tone={meta.tone}>{meta.label}</Tag>
      </div>
      {item.subtitle && (
        <div style={{ fontSize: 12, color: "var(--ink-3)", lineHeight: 1.5 }}>{item.subtitle}</div>
      )}
      <div
        style={{
          marginTop: "auto",
          display: "flex",
          flexWrap: "wrap",
          gap: 6,
          color: "var(--ink-3)",
          fontSize: 11,
        }}
      >
        <span>📁 {item.project_name || "未知项目"}</span>
        {item.created_by_name && (
          <>
            <span>·</span>
            <span>✍ {item.created_by_name}</span>
          </>
        )}
      </div>
    </article>
  );
}

function GroupBlock({
  label,
  items,
  emptyHint,
}: {
  label: string;
  items: PublicAssetItem[];
  emptyHint: string;
}) {
  return (
    <section style={{ marginBottom: 24 }}>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          marginBottom: 10,
        }}
      >
        <h3 style={{ margin: 0, fontSize: 14, fontWeight: 700, color: "var(--ink)" }}>{label}</h3>
        <Tag tone="neutral">{items.length}</Tag>
      </div>
      {items.length === 0 ? (
        <div
          style={{
            padding: "20px 12px",
            textAlign: "center",
            color: "var(--ink-3)",
            fontSize: 13,
            border: "1px dashed var(--line)",
            borderRadius: 8,
            background: "var(--bg)",
          }}
        >
          {emptyHint}
        </div>
      ) : (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))",
            gap: 12,
          }}
        >
          {items.map((item) => (
            <AssetCard key={`${item.object_type}-${item.object_id}`} item={item} />
          ))}
        </div>
      )}
    </section>
  );
}

function totalCount(out: PublicAssetsOut | null): number {
  if (!out) return 0;
  return out.cards.length + out.business_objects.length + out.visits.length;
}

export function PublicAssetsView() {
  const [pub, setPub] = useState<PublicAssetsOut | null>(null);
  const [shared, setShared] = useState<PublicAssetsOut | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [p, s] = await Promise.all([api.listPublicAssets(), api.listSharedWithMe()]);
      setPub(p);
      setShared(s);
    } catch (e) {
      // 静默错误：辅助视图，不阻塞团队空间主流程
      setError((e as Error).message || "加载公开资产失败");
      setPub(null);
      setShared(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading && !pub) {
    return (
      <div style={{ display: "flex", alignItems: "center", gap: 8, color: "var(--ink-3)", fontSize: 13, padding: 12 }}>
        <Spinner size={14} /> 加载中…
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
        <div style={{ color: "var(--danger)", fontSize: 13 }}>{error}</div>
        <Btn variant="secondary" icon={<I.Refresh size={14} />} onClick={load}>
          重试
        </Btn>
      </div>
    );
  }

  const sharedCount = totalCount(shared);

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 12 }}>
        <Btn
          variant="secondary"
          size="sm"
          icon={loading ? <I.Loader size={13} /> : <I.Refresh size={13} />}
          onClick={load}
          disabled={loading}
        >
          刷新
        </Btn>
      </div>

      <GroupBlock
        label="公开资产"
        items={[
          ...(pub?.cards ?? []),
          ...(pub?.business_objects ?? []),
          ...(pub?.visits ?? []),
        ]}
        emptyHint="暂无公开资产。在角色卡 / 业务地图 / 拜访记录详情中标记「完全公开」后，对象会汇集于此。"
      />

      <GroupBlock
        label={`共享给我的${sharedCount ? `（${sharedCount}）` : ""}`}
        items={[
          ...(shared?.cards ?? []),
          ...(shared?.business_objects ?? []),
          ...(shared?.visits ?? []),
        ]}
        emptyHint="暂无他人共享给你的对象。"
      />
    </div>
  );
}
