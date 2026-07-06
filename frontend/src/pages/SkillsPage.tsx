// 技能与插件管理页面:列表 + 文件编辑弹窗
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Category, FileNode, Plugin, Skill } from "@/types";
import { api } from "@/api/client";
import { I } from "@/icons";
import {
  Btn,
  Card,
  ConfirmDialog,
  Input,
  Spinner,
  TextArea,
} from "@/components/ui";

type TabKey = "skills" | "plugins" | "categories";

interface EditingItem {
  name: string;
  type: "skill" | "plugin";
}

interface SelectedFile {
  path: string;
  content: string;
}

interface DeleteTarget {
  name: string;
  type: "skill" | "plugin";
  references?: AgentRef[];
}

interface AgentRef {
  id: number;
  name: string;
  code: string;
}


export default function SkillsPage() {
  const [tab, setTab] = useState<TabKey>("skills");
  const [skills, setSkills] = useState<Skill[]>([]);
  const [plugins, setPlugins] = useState<Plugin[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchKw, setSearchKw] = useState("");

  // 弹窗状态
  const [editingItem, setEditingItem] = useState<EditingItem | null>(null);
  const [fileTree, setFileTree] = useState<FileNode | null>(null);
  const [fileTreeLoading, setFileTreeLoading] = useState(false);
  const [selectedFile, setSelectedFile] = useState<SelectedFile | null>(null);
  const [fileContent, setFileContent] = useState("");
  const [savingFile, setSavingFile] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [fileErr, setFileErr] = useState<string | null>(null);

  // 删除状态
  const [deleteTarget, setDeleteTarget] = useState<DeleteTarget | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [savingCategoryKey, setSavingCategoryKey] = useState<string | null>(null);

  // 新建文件弹窗(仅技能)
  const [creatingFile, setCreatingFile] = useState(false);
  const [newFilePath, setNewFilePath] = useState("");
  const [creatingFileLoading, setCreatingFileLoading] = useState(false);

  // 上传
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [showUploadCategoryDialog, setShowUploadCategoryDialog] = useState(false);
  const [selectedUploadCategoryId, setSelectedUploadCategoryId] = useState<number | null>(null);

  // 分类管理状态
  const [newCategoryName, setNewCategoryName] = useState("");
  const [creatingCategory, setCreatingCategory] = useState(false);
  const [renamingCategory, setRenamingCategory] = useState<Category | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [deletingCategoryId, setDeletingCategoryId] = useState<number | null>(null);

  // 加载列表
  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const [sk, pl, cats] = await Promise.all([
        api.skills(),
        api.plugins(),
        api.categories(),
      ]);
      setSkills(sk);
      setPlugins(pl);
      setCategories(cats);
    } catch {
      // 静默
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  // 过滤
  const filteredSkills = useMemo(() => {
    const kw = searchKw.trim().toLowerCase();
    if (!kw) return skills;
    return skills.filter(
      (s) =>
        s.name.toLowerCase().includes(kw) ||
        (s.description || "").toLowerCase().includes(kw),
    );
  }, [skills, searchKw]);

  const filteredPlugins = useMemo(() => {
    const kw = searchKw.trim().toLowerCase();
    if (!kw) return plugins;
    return plugins.filter(
      (p) =>
        p.name.toLowerCase().includes(kw) ||
        (p.description || "").toLowerCase().includes(kw),
    );
  }, [plugins, searchKw]);

  const currentList = tab === "skills" ? filteredSkills : tab === "plugins" ? filteredPlugins : [];
  const currentCount = tab === "skills" ? skills.length : tab === "plugins" ? plugins.length : categories.length;

  // 按分类分组
  const groupedSkills = useMemo(() => {
    const map = new Map<string, Skill[]>();
    for (const s of filteredSkills) {
      const cat = s.category || "默认";
      if (!map.has(cat)) map.set(cat, []);
      map.get(cat)!.push(s);
    }
    return Array.from(map.entries()).map(([category, items]) => ({ category, items }));
  }, [filteredSkills]);

  const groupedPlugins = useMemo(() => {
    const map = new Map<string, Plugin[]>();
    for (const p of filteredPlugins) {
      const cat = p.category || "默认";
      if (!map.has(cat)) map.set(cat, []);
      map.get(cat)!.push(p);
    }
    return Array.from(map.entries()).map(([category, items]) => ({ category, items }));
  }, [filteredPlugins]);

  // 打开编辑/查看弹窗
  const openEdit = async (name: string, type: "skill" | "plugin") => {
    setEditingItem({ name, type });
    setFileTree(null);
    setSelectedFile(null);
    setFileContent("");
    setFileErr(null);
    setFileTreeLoading(true);
    try {
      const tree =
        type === "skill"
          ? await api.adminSkillFiles(name)
          : await api.adminPluginFiles(name);
      setFileTree(tree);
      // 自动选中第一个文件
      const firstFile = findFirstFile(tree);
      if (firstFile) {
        await selectFile(firstFile, type, name);
      }
    } catch (e) {
      setFileErr((e as Error).message || "加载文件树失败");
    } finally {
      setFileTreeLoading(false);
    }
  };

  const closeEdit = () => {
    if (savingFile || creatingFileLoading) return;
    setEditingItem(null);
    setFileTree(null);
    setSelectedFile(null);
    setFileContent("");
    setFileErr(null);
    setCreatingFile(false);
    setNewFilePath("");
  };

  // 选中文件并加载内容
  const selectFile = async (path: string, type: string, name: string) => {
    setFileErr(null);
    try {
      const content =
        type === "skill"
          ? await api.adminSkillFileContent(name, path)
          : await api.adminPluginFileContent(name, path);
      setSelectedFile({ path, content });
      setFileContent(content);
    } catch (e) {
      setFileErr((e as Error).message || "读取文件失败");
    }
  };

  // 保存文件(仅技能)
  const saveFile = async () => {
    if (!editingItem || editingItem.type !== "skill" || !selectedFile) return;
    setSavingFile(true);
    setFileErr(null);
    try {
      await api.adminWriteSkillFile(
        editingItem.name,
        selectedFile.path,
        fileContent,
      );
      setSelectedFile({ ...selectedFile, content: fileContent });
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 1200);
    } catch (e) {
      setFileErr((e as Error).message || "保存失败");
    } finally {
      setSavingFile(false);
    }
  };

  // 删除技能/插件
  const askDelete = async (name: string, type: "skill" | "plugin") => {
    setDeleteTarget({ name, type });
  };

  const doDelete = async (force?: boolean) => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      if (deleteTarget.type === "skill") {
        await api.adminDeleteSkill(deleteTarget.name, force);
      } else {
        await api.adminDeletePlugin(deleteTarget.name, force);
      }
      setDeleteTarget(null);
      await reload();
    } catch (e) {
      const err = e as Error & { status?: number; detail?: unknown };
      // 409 时后端返回 { detail: { message, agents: [...] } }
      if (err.status === 409 || err.message.includes("409")) {
        try {
          // 尝试从错误消息中解析 JSON
          const match = err.message.match(/409:\s*(.+)/);
          if (match) {
            const data = JSON.parse(match[1]) as {
              detail?: { message?: string; agents?: AgentRef[] };
            };
            const refs = data.detail?.agents;
            if (refs && refs.length > 0) {
              setDeleteTarget({ ...deleteTarget, references: refs });
              return;
            }
          }
        } catch {
          // 解析失败则回退到普通错误
        }
      }
      alert("删除失败: " + (err.message || ""));
      setDeleteTarget(null);
    } finally {
      setDeleting(false);
    }
  };

  // 修改技能/插件分类
  const changeItemCategory = async (
    type: "skill" | "plugin",
    key: string,
    categoryId: number,
  ) => {
    const category = categories.find((c) => c.id === categoryId);
    if (!category) return;

    const savingKey = `${type}:${key}`;
    setSavingCategoryKey(savingKey);
    try {
      if (type === "skill") {
        await api.adminUpdateSkillCategory(key, categoryId);
        setSkills((prev) =>
          prev.map((item) =>
            item.name === key ? { ...item, category: category.name } : item,
          ),
        );
      } else {
        await api.adminUpdatePluginCategory(key, categoryId);
        setPlugins((prev) =>
          prev.map((item) =>
            item.path === key ? { ...item, category: category.name } : item,
          ),
        );
      }
    } catch (err) {
      alert("修改分类失败: " + ((err as Error).message || ""));
    } finally {
      setSavingCategoryKey(null);
    }
  };

  // 上传 ZIP
  const triggerUpload = () => {
    const defaultCat = categories.find((c) => c.name === "默认");
    setSelectedUploadCategoryId(defaultCat?.id ?? categories[0]?.id ?? null);
    setShowUploadCategoryDialog(true);
  };

  const confirmUploadCategory = () => {
    setShowUploadCategoryDialog(false);
    // 延迟触发文件选择，确保对话框已关闭
    setTimeout(() => fileInputRef.current?.click(), 50);
  };

  const onFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || selectedUploadCategoryId == null) return;
    setUploading(true);
    try {
      if (tab === "skills") {
        await api.adminUploadSkill(file, selectedUploadCategoryId);
      } else {
        await api.adminUploadPlugin(file, selectedUploadCategoryId);
      }
      await reload();
    } catch (err) {
      alert("上传失败: " + ((err as Error).message || ""));
    } finally {
      setUploading(false);
      e.target.value = "";
    }
  };

  // 分类管理操作
  const createCategory = async () => {
    const name = newCategoryName.trim();
    if (!name) return;
    setCreatingCategory(true);
    try {
      await api.createCategory(name);
      setNewCategoryName("");
      await reload();
    } catch (err) {
      alert("创建失败: " + ((err as Error).message || ""));
    } finally {
      setCreatingCategory(false);
    }
  };

  const doRenameCategory = async () => {
    if (!renamingCategory || !renameValue.trim()) return;
    try {
      await api.renameCategory(renamingCategory.id, renameValue.trim());
      setRenamingCategory(null);
      setRenameValue("");
      await reload();
    } catch (err) {
      alert("重命名失败: " + ((err as Error).message || ""));
    }
  };

  const doDeleteCategory = async () => {
    if (!deletingCategoryId) return;
    try {
      await api.deleteCategory(deletingCategoryId);
      setDeletingCategoryId(null);
      await reload();
    } catch (err) {
      alert("删除失败: " + ((err as Error).message || ""));
    }
  };

  // 新建文件(仅技能)
  const createNewFile = async () => {
    if (!editingItem || editingItem.type !== "skill") return;
    const path = newFilePath.trim();
    if (!path) {
      setFileErr("请输入文件路径");
      return;
    }
    setCreatingFileLoading(true);
    setFileErr(null);
    try {
      await api.adminCreateSkillFile(editingItem.name, path, "");
      setCreatingFile(false);
      setNewFilePath("");
      // 刷新文件树并选中新文件
      const tree = await api.adminSkillFiles(editingItem.name);
      setFileTree(tree);
      await selectFile(path, "skill", editingItem.name);
    } catch (e) {
      setFileErr((e as Error).message || "创建文件失败");
    } finally {
      setCreatingFileLoading(false);
    }
  };

  // 删除文件(仅技能)
  const deleteSkillFile = async (path: string) => {
    if (!editingItem || editingItem.type !== "skill") return;
    setFileErr(null);
    try {
      await api.adminDeleteSkillFile(editingItem.name, path);
      // 刷新文件树
      const tree = await api.adminSkillFiles(editingItem.name);
      setFileTree(tree);
      if (selectedFile?.path === path) {
        setSelectedFile(null);
        setFileContent("");
        // 自动选中下一个文件
        const next = findFirstFile(tree);
        if (next) await selectFile(next, "skill", editingItem.name);
      }
    } catch (e) {
      setFileErr((e as Error).message || "删除文件失败");
    }
  };

  return (
    <div style={{ flex: 1, display: "flex", overflow: "hidden" }}>
      {/* 主列表区 */}
      <div
        style={{
          flex: 1,
          overflow: "auto",
          padding: "24px 28px",
          minWidth: 0,
        }}
      >
        {/* 标题栏 */}
        <div
          style={{
            display: "flex",
            alignItems: "flex-end",
            justifyContent: "space-between",
            marginBottom: 18,
            gap: 12,
            flexWrap: "wrap",
          }}
        >
          <div style={{ minWidth: 0 }}>
            <h1
              style={{
                fontFamily: "var(--serif)",
                fontSize: 24,
                fontWeight: 500,
                marginBottom: 4,
                color: "var(--ink)",
                letterSpacing: -0.01,
              }}
            >
              {tab === "categories"
                ? "分类管理"
                : tab === "plugins"
                  ? "插件管理"
                  : "技能管理"}{" "}
              <span
                style={{
                  fontSize: 14,
                  color: "var(--ink-3)",
                  fontWeight: 400,
                  fontFamily: "var(--sans)",
                }}
              >
                · 共 {currentCount} 个
              </span>
            </h1>
            <div style={{ fontSize: 13, color: "var(--ink-3)" }}>
              {tab === "categories"
                ? "管理技能和插件的分类"
                : "管理全局技能与插件"}
            </div>
          </div>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <Input
              icon={<I.Search size={14} />}
              placeholder="搜索"
              value={searchKw}
              onChange={(e) => setSearchKw(e.target.value)}
              containerStyle={{ width: 220, height: 34 }}
            />
            {tab !== "categories" && (
              <>
                <Btn
                  variant="primary"
                  icon={uploading ? <I.Loader size={14} /> : <I.Upload size={14} />}
                  onClick={triggerUpload}
                  disabled={uploading}
                >
                  {uploading ? "上传中…" : "上传 ZIP"}
                </Btn>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".zip"
                  onChange={onFileChange}
                  style={{ display: "none" }}
                />
              </>
            )}
          </div>
        </div>

        {/* Tab 切换 */}
        <div
          style={{
            display: "flex",
            gap: 4,
            marginBottom: 16,
            borderBottom: "1px solid var(--line)",
          }}
        >
          <TabButton
            active={tab === "skills"}
            label={`技能管理 · ${skills.length}`}
            onClick={() => {
              setTab("skills");
              setSearchKw("");
            }}
          />
          <TabButton
            active={tab === "plugins"}
            label={`插件管理 · ${plugins.length}`}
            onClick={() => {
              setTab("plugins");
              setSearchKw("");
            }}
          />
          <TabButton
            active={tab === "categories"}
            label={`分类管理 · ${categories.length}`}
            onClick={() => {
              setTab("categories");
              setSearchKw("");
            }}
          />
        </div>

        {/* 列表内容 */}
        {loading ? (
          <div
            style={{
              padding: 60,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: 10,
              color: "var(--ink-3)",
              fontSize: 13,
            }}
          >
            <Spinner /> 加载中…
          </div>
        ) : tab === "categories" ? (
          <CategoryManager
            categories={categories}
            newCategoryName={newCategoryName}
            setNewCategoryName={setNewCategoryName}
            creatingCategory={creatingCategory}
            onCreateCategory={createCategory}
            renamingCategory={renamingCategory}
            setRenamingCategory={setRenamingCategory}
            renameValue={renameValue}
            setRenameValue={setRenameValue}
            onRenameCategory={doRenameCategory}
            deletingCategoryId={deletingCategoryId}
            setDeletingCategoryId={setDeletingCategoryId}
            onDeleteCategory={doDeleteCategory}
          />
        ) : currentList.length === 0 ? (
          <EmptyState
            searched={!!searchKw}
            type={tab}
            onUpload={triggerUpload}
          />
        ) : tab === "skills" ? (
          <GroupedItemList
            groups={groupedSkills}
            type="skill"
            categories={categories}
            savingCategoryKey={savingCategoryKey}
            onEdit={openEdit}
            onDelete={askDelete}
            onCategoryChange={changeItemCategory}
          />
        ) : (
          <GroupedItemList
            groups={groupedPlugins}
            type="plugin"
            categories={categories}
            savingCategoryKey={savingCategoryKey}
            onEdit={openEdit}
            onDelete={askDelete}
            onCategoryChange={changeItemCategory}
          />
        )}
      </div>

      {/* 编辑/查看弹窗 */}
      {editingItem && (
        <EditModal
          item={editingItem}
          fileTree={fileTree}
          fileTreeLoading={fileTreeLoading}
          selectedFile={selectedFile}
          fileContent={fileContent}
          savingFile={savingFile}
          saveSuccess={saveSuccess}
          fileErr={fileErr}
          onClose={closeEdit}
          onSelectFile={(path) =>
            selectFile(path, editingItem.type, editingItem.name)
          }
          onFileContentChange={setFileContent}
          onSaveFile={saveFile}
          onCreateFile={() => setCreatingFile(true)}
          onDeleteFile={deleteSkillFile}
          onRefreshTree={async () => {
            if (!editingItem) return;
            setFileTreeLoading(true);
            try {
              const tree =
                editingItem.type === "skill"
                  ? await api.adminSkillFiles(editingItem.name)
                  : await api.adminPluginFiles(editingItem.name);
              setFileTree(tree);
            } catch (e) {
              setFileErr((e as Error).message || "刷新失败");
            } finally {
              setFileTreeLoading(false);
            }
          }}
        />
      )}

      {/* 新建文件弹窗 */}
      {creatingFile && editingItem?.type === "skill" && (
        <>
          <div
            onClick={() => {
              if (!creatingFileLoading) {
                setCreatingFile(false);
                setNewFilePath("");
              }
            }}
            style={{
              position: "fixed",
              inset: 0,
              background: "rgba(0,0,0,0.32)",
              zIndex: 42,
              animation: "fade 160ms ease",
            }}
          />
          <div
            role="dialog"
            aria-modal="true"
            style={{
              position: "fixed",
              inset: 0,
              zIndex: 43,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              padding: 24,
              pointerEvents: "none",
            }}
          >
            <div
              style={{
                pointerEvents: "auto",
                width: "min(400px, 100%)",
                background: "var(--bg)",
                border: "1px solid var(--line)",
                borderRadius: 12,
                boxShadow: "var(--shadow-lg)",
                padding: "20px 20px 16px",
                display: "flex",
                flexDirection: "column",
                gap: 14,
              }}
            >
              <h3
                style={{
                  fontFamily: "var(--serif)",
                  fontSize: 16,
                  fontWeight: 500,
                  color: "var(--ink)",
                  margin: 0,
                }}
              >
                新建文件
              </h3>
              <Input
                placeholder="例如: tools/new_tool.py"
                value={newFilePath}
                onChange={(e) => setNewFilePath(e.target.value)}
                autoFocus
              />
              <div
                style={{
                  display: "flex",
                  justifyContent: "flex-end",
                  gap: 8,
                }}
              >
                <Btn
                  variant="ghost"
                  onClick={() => {
                    setCreatingFile(false);
                    setNewFilePath("");
                  }}
                  disabled={creatingFileLoading}
                >
                  取消
                </Btn>
                <Btn
                  variant="primary"
                  onClick={createNewFile}
                  disabled={creatingFileLoading || !newFilePath.trim()}
                >
                  {creatingFileLoading ? "创建中…" : "创建"}
                </Btn>
              </div>
            </div>
          </div>
        </>
      )}

      {/* 删除确认弹窗 */}
      <ConfirmDialog
        open={!!deleteTarget && !deleteTarget.references}
        title={`确认删除${deleteTarget?.type === "skill" ? "技能" : "插件"}`}
        message={
          deleteTarget
            ? `确认删除 "${deleteTarget.name}"? 此操作不可恢复。`
            : ""
        }
        confirmText="删除"
        variant="danger"
        onConfirm={() => doDelete()}
        onCancel={() => setDeleteTarget(null)}
      />

      {/* 强制删除弹窗(有引用时) */}
      {deleteTarget?.references && (
        <>
          <div
            onClick={() => {
              if (!deleting) setDeleteTarget(null);
            }}
            style={{
              position: "fixed",
              inset: 0,
              background: "rgba(0,0,0,0.32)",
              zIndex: 50,
              animation: "fade 160ms ease",
            }}
          />
          <div
            role="dialog"
            aria-modal="true"
            style={{
              position: "fixed",
              inset: 0,
              zIndex: 51,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              padding: 24,
              pointerEvents: "none",
            }}
          >
            <div
              style={{
                pointerEvents: "auto",
                width: "min(460px, 100%)",
                background: "var(--bg)",
                border: "1px solid var(--line)",
                borderRadius: 12,
                boxShadow: "var(--shadow-lg)",
                padding: "24px 20px 20px",
                display: "flex",
                flexDirection: "column",
                gap: 16,
              }}
            >
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 10,
                }}
              >
                <I.AlertTriangle size={20} style={{ color: "var(--danger)" }} />
                <h3
                  style={{
                    fontFamily: "var(--serif)",
                    fontSize: 16,
                    fontWeight: 500,
                    color: "var(--ink)",
                    margin: 0,
                  }}
                >
                  无法删除
                </h3>
              </div>
              <p style={{ fontSize: 14, color: "var(--ink-2)", margin: 0 }}>
                {deleteTarget.type === "skill"
                  ? `技能 "${deleteTarget.name}" 正被以下智能体引用:`
                  : `插件 "${deleteTarget.name}" 正被以下智能体引用:`}
              </p>
              <div
                style={{
                  display: "flex",
                  flexDirection: "column",
                  gap: 6,
                  maxHeight: 200,
                  overflow: "auto",
                  padding: 10,
                  background: "var(--bg-2)",
                  border: "1px solid var(--line)",
                  borderRadius: 8,
                }}
              >
                {deleteTarget.references.map((a) => (
                  <div
                    key={a.id}
                    style={{
                      fontSize: 13,
                      color: "var(--ink)",
                      display: "flex",
                      alignItems: "center",
                      gap: 8,
                    }}
                  >
                    <span
                      style={{
                        width: 6,
                        height: 6,
                        borderRadius: 999,
                        background: "var(--accent)",
                      }}
                    />
                    <span style={{ fontWeight: 500 }}>{a.name}</span>
                    <code
                      style={{
                        fontFamily: "var(--mono)",
                        fontSize: 11,
                        color: "var(--ink-3)",
                        background: "var(--bg-3)",
                        padding: "1px 5px",
                        borderRadius: 4,
                      }}
                    >
                      {a.code}
                    </code>
                  </div>
                ))}
              </div>
              <div
                style={{
                  display: "flex",
                  justifyContent: "flex-end",
                  gap: 8,
                }}
              >
                <Btn
                  variant="ghost"
                  onClick={() => setDeleteTarget(null)}
                  disabled={deleting}
                >
                  取消
                </Btn>
                <Btn
                  variant="danger"
                  onClick={() => doDelete(true)}
                  disabled={deleting}
                >
                  {deleting ? "删除中…" : "强制删除"}
                </Btn>
              </div>
            </div>
          </div>
        </>
      )}

      {/* 上传分类选择弹窗 */}
      {showUploadCategoryDialog && (
        <>
          <div
            onClick={() => setShowUploadCategoryDialog(false)}
            style={{
              position: "fixed",
              inset: 0,
              background: "rgba(0,0,0,0.32)",
              zIndex: 50,
              animation: "fade 160ms ease",
            }}
          />
          <div
            role="dialog"
            aria-modal="true"
            style={{
              position: "fixed",
              inset: 0,
              zIndex: 51,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              padding: 24,
              pointerEvents: "none",
            }}
          >
            <div
              style={{
                pointerEvents: "auto",
                width: "min(400px, 100%)",
                background: "var(--bg)",
                border: "1px solid var(--line)",
                borderRadius: 12,
                boxShadow: "var(--shadow-lg)",
                padding: "20px 20px 16px",
                display: "flex",
                flexDirection: "column",
                gap: 14,
              }}
            >
              <h3
                style={{
                  fontFamily: "var(--serif)",
                  fontSize: 16,
                  fontWeight: 500,
                  color: "var(--ink)",
                  margin: 0,
                }}
              >
                选择分类
              </h3>
              <div
                style={{
                  display: "flex",
                  flexDirection: "column",
                  gap: 6,
                  maxHeight: 240,
                  overflow: "auto",
                }}
              >
                {categories.map((cat) => (
                  <label
                    key={cat.id}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 8,
                      padding: "8px 10px",
                      borderRadius: 8,
                      cursor: "pointer",
                      background:
                        selectedUploadCategoryId === cat.id
                          ? "var(--accent-soft)"
                          : "transparent",
                      transition: "background 120ms",
                    }}
                  >
                    <input
                      type="radio"
                      name="upload-category"
                      checked={selectedUploadCategoryId === cat.id}
                      onChange={() => setSelectedUploadCategoryId(cat.id)}
                    />
                    <span style={{ fontSize: 14, color: "var(--ink)" }}>
                      {cat.name}
                    </span>
                  </label>
                ))}
              </div>
              <div
                style={{
                  display: "flex",
                  justifyContent: "flex-end",
                  gap: 8,
                }}
              >
                <Btn
                  variant="ghost"
                  onClick={() => setShowUploadCategoryDialog(false)}
                >
                  取消
                </Btn>
                <Btn
                  variant="primary"
                  onClick={confirmUploadCategory}
                  disabled={selectedUploadCategoryId == null}
                >
                  确认
                </Btn>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

// ============ Tab 按钮 ============
function TabButton({
  active,
  label,
  onClick,
}: {
  active: boolean;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className="focus-ring"
      style={{
        padding: "8px 14px",
        fontSize: 13,
        fontWeight: active ? 500 : 400,
        color: active ? "var(--accent)" : "var(--ink-2)",
        borderBottom: active ? "2px solid var(--accent)" : "2px solid transparent",
        background: "transparent",
        border: "none",
        borderBottomColor: active ? "var(--accent)" : "transparent",
        cursor: "pointer",
        transition: "color 120ms, border-color 120ms",
        marginBottom: -1,
      }}
    >
      {label}
    </button>
  );
}

// ============ 卡片 ============
function ItemCard({
  name,
  description,
  fileCount,
  type,
  category,
  categories,
  savingCategory,
  onEdit,
  onDelete,
  onCategoryChange,
}: {
  name: string;
  description: string;
  fileCount: number;
  type: "skill" | "plugin";
  category: string;
  categories: Category[];
  savingCategory: boolean;
  onEdit: () => void;
  onDelete: () => void;
  onCategoryChange: (categoryId: number) => void;
}) {
  const [categoryMenuOpen, setCategoryMenuOpen] = useState(false);

  const currentCategory = category || "默认";

  return (
    <Card
      style={{
        position: "relative",
        padding: 16,
        display: "flex",
        flexDirection: "column",
        gap: 12,
        transition: "border-color 120ms, box-shadow 120ms",
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.borderColor = "var(--line-2)";
        e.currentTarget.style.boxShadow = "var(--shadow-sm)";
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.borderColor = "var(--line)";
        e.currentTarget.style.boxShadow = "none";
      }}
    >
      {/* 头部 */}
      <div style={{ display: "flex", alignItems: "flex-start", gap: 10 }}>
        <span
          style={{
            width: 36,
            height: 36,
            borderRadius: 10,
            background: "var(--accent-soft)",
            color: "var(--accent)",
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            flexShrink: 0,
          }}
        >
          {type === "skill" ? <I.Sparkles size={18} /> : <I.Puzzle size={18} />}
        </span>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div
            style={{
              fontSize: 14.5,
              fontWeight: 600,
              color: "var(--ink)",
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
              marginBottom: 2,
            }}
          >
            {name}
          </div>
          <div style={{ fontSize: 12, color: "var(--ink-3)" }}>
            {fileCount > 0 ? `${fileCount} 个文件` : " "}
          </div>
        </div>
      </div>

      {/* 描述 */}
      {description && (
        <div
          style={{
            fontSize: 12.5,
            color: "var(--ink-2)",
            lineHeight: 1.55,
            maxHeight: 64,
            overflow: "hidden",
            display: "-webkit-box",
            WebkitLineClamp: 3,
            WebkitBoxOrient: "vertical",
          }}
        >
          {description}
        </div>
      )}

      {/* 底部操作 */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          paddingTop: 8,
          borderTop: "1px solid var(--line)",
          marginTop: "auto",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 6,
            minWidth: 0,
          }}
        >
          <span
            style={{
              fontSize: 11,
              color: "var(--ink-3)",
              fontFamily: "var(--mono)",
              flexShrink: 0,
            }}
          >
            {type === "skill" ? "SKILL" : "PLUGIN"}
          </span>
          <span style={{ fontSize: 11, color: "var(--ink-3)" }}>·</span>
          <button
            type="button"
            className="focus-ring"
            disabled={savingCategory || categories.length === 0}
            onClick={() => setCategoryMenuOpen((v) => !v)}
            title="修改分类"
            style={{
              maxWidth: 150,
              minWidth: 0,
              display: "inline-flex",
              alignItems: "center",
              gap: 4,
              padding: "2px 7px",
              border: "1px solid var(--line)",
              borderRadius: 999,
              background: categoryMenuOpen ? "var(--bg-3)" : "var(--bg-2)",
              color: "var(--ink-2)",
              fontSize: 11.5,
              cursor: savingCategory || categories.length === 0 ? "default" : "pointer",
              transition: "background 120ms, border-color 120ms, color 120ms",
            }}
          >
            {savingCategory ? (
              <I.Loader size={12} />
            ) : (
              <I.Folder size={12} />
            )}
            <span
              style={{
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
            >
              {currentCategory}
            </span>
            {!savingCategory && <I.ChevronDown size={12} />}
          </button>
          {categoryMenuOpen && (
            <div
              style={{
                position: "absolute",
                left: 16,
                bottom: 44,
                width: 190,
                maxHeight: 240,
                overflow: "auto",
                padding: 6,
                border: "1px solid var(--line)",
                borderRadius: 8,
                background: "var(--surface)",
                boxShadow: "0 12px 32px rgba(31, 27, 23, 0.14)",
                zIndex: 10,
              }}
            >
              {categories.map((cat) => {
                const active = cat.name === currentCategory;
                return (
                  <button
                    key={cat.id}
                    type="button"
                    className="focus-ring"
                    onClick={() => {
                      setCategoryMenuOpen(false);
                      if (!active) onCategoryChange(cat.id);
                    }}
                    style={{
                      width: "100%",
                      minHeight: 30,
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      gap: 8,
                      padding: "6px 8px",
                      border: "none",
                      borderRadius: 6,
                      background: active ? "var(--accent-soft)" : "transparent",
                      color: active ? "var(--accent)" : "var(--ink-2)",
                      fontSize: 12,
                      textAlign: "left",
                      cursor: active ? "default" : "pointer",
                    }}
                  >
                    <span
                      style={{
                        minWidth: 0,
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                      }}
                    >
                      {cat.name}
                    </span>
                    {active && <I.Check size={13} />}
                  </button>
                );
              })}
            </div>
          )}
        </div>
        <div style={{ display: "flex", gap: 4 }}>
          <button
            onClick={onEdit}
            title={type === "skill" ? "编辑" : "查看"}
            className="focus-ring"
            style={iconBtnStyle}
          >
            {type === "skill" ? <I.Edit size={14} /> : <I.Eye size={14} />}
          </button>
          <button
            onClick={onDelete}
            title="删除"
            className="focus-ring"
            style={{
              ...iconBtnStyle,
              color: "var(--danger)",
            }}
          >
            <I.Trash size={14} />
          </button>
        </div>
      </div>
    </Card>
  );
}

// ============ 编辑/查看弹窗 ============
function EditModal({
  item,
  fileTree,
  fileTreeLoading,
  selectedFile,
  fileContent,
  savingFile,
  saveSuccess,
  fileErr,
  onClose,
  onSelectFile,
  onFileContentChange,
  onSaveFile,
  onCreateFile,
  onDeleteFile,
  onRefreshTree,
}: {
  item: EditingItem;
  fileTree: FileNode | null;
  fileTreeLoading: boolean;
  selectedFile: SelectedFile | null;
  fileContent: string;
  savingFile: boolean;
  saveSuccess: boolean;
  fileErr: string | null;
  onClose: () => void;
  onSelectFile: (path: string) => void;
  onFileContentChange: (v: string) => void;
  onSaveFile: () => void;
  onCreateFile: () => void;
  onDeleteFile: (path: string) => void;
  onRefreshTree: () => void;
}) {
  const isSkill = item.type === "skill";
  const title = isSkill ? `编辑技能: ${item.name}` : `查看插件: ${item.name}`;
  const [confirmingDeletePath, setConfirmingDeletePath] = useState<string | null>(null);
  const [deletingFilePath, setDeletingFilePath] = useState<string | null>(null);

  useEffect(() => {
    setConfirmingDeletePath(null);
    setDeletingFilePath(null);
  }, [item.name]);

  const confirmDeleteFile = async (path: string) => {
    setDeletingFilePath(path);
    try {
      await onDeleteFile(path);
      setConfirmingDeletePath(null);
    } finally {
      setDeletingFilePath(null);
    }
  };

  return (
    <>
      {/* 遮罩 */}
      <div
        onClick={onClose}
        style={{
          position: "fixed",
          inset: 0,
          background: "rgba(0,0,0,0.32)",
          zIndex: 40,
          animation: "fade 160ms ease",
        }}
      />
      {/* 居中弹窗本体 */}
      <div
        role="dialog"
        aria-modal="true"
        style={{
          position: "fixed",
          inset: 0,
          zIndex: 41,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          padding: 24,
          pointerEvents: "none",
        }}
      >
        <div
          style={{
            pointerEvents: "auto",
            width: "85vw",
            height: "85vh",
            background: "var(--bg)",
            border: "1px solid var(--line)",
            borderRadius: 12,
            boxShadow: "var(--shadow-lg)",
            display: "flex",
            flexDirection: "column",
            overflow: "hidden",
          }}
        >
          {/* 顶部标题栏 */}
          <div
            style={{
              padding: "16px 20px",
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              borderBottom: "1px solid var(--line)",
              flexShrink: 0,
            }}
          >
            <h2
              style={{
                fontFamily: "var(--serif)",
                fontSize: 17,
                fontWeight: 500,
                color: "var(--ink)",
              }}
            >
              {title}
            </h2>
            <button
              onClick={onClose}
              className="focus-ring"
              title="关闭"
              style={{
                background: "transparent",
                border: "none",
                color: "var(--ink-3)",
                cursor: "pointer",
                padding: 6,
                borderRadius: 6,
                display: "flex",
              }}
            >
              <I.X size={16} />
            </button>
          </div>

          {/* 错误提示 */}
          {fileErr && (
            <div
              style={{
                background: "var(--danger-soft)",
                color: "var(--danger)",
                padding: "8px 16px",
                fontSize: 13,
                display: "flex",
                alignItems: "center",
                gap: 8,
                flexShrink: 0,
              }}
            >
              <I.CircleAlert size={14} />
              {fileErr}
            </div>
          )}

          {/* 左导航 + 主内容 */}
          <div
            style={{
              flex: 1,
              display: "flex",
              minHeight: 0,
            }}
          >
            {/* 左侧文件树 */}
            <div
              style={{
                width: 240,
                flexShrink: 0,
                borderRight: "1px solid var(--line)",
                display: "flex",
                flexDirection: "column",
                background: "var(--bg-2)",
              }}
            >
              {/* 文件树头部按钮 */}
              {isSkill && (
                <div
                  style={{
                    display: "flex",
                    gap: 4,
                    padding: "8px 10px",
                    borderBottom: "1px solid var(--line)",
                  }}
                >
                  <button
                    onClick={onCreateFile}
                    className="focus-ring"
                    style={{
                      ...smallBtnStyle,
                      flex: 1,
                    }}
                    title="新建文件"
                  >
                    <I.Plus size={12} />
                    新建文件
                  </button>
                  <button
                    onClick={onRefreshTree}
                    disabled={fileTreeLoading}
                    className="focus-ring"
                    style={smallBtnStyle}
                    title="刷新"
                  >
                    {fileTreeLoading ? (
                      <I.Loader size={12} />
                    ) : (
                      <I.Refresh size={12} />
                    )}
                  </button>
                </div>
              )}
              <div
                style={{
                  flex: 1,
                  overflow: "auto",
                  padding: "6px 4px 16px",
                }}
              >
                {fileTreeLoading ? (
                  <div
                    style={{
                      padding: 20,
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      gap: 8,
                      color: "var(--ink-3)",
                      fontSize: 12,
                    }}
                  >
                    <Spinner size={12} /> 加载中…
                  </div>
                ) : fileTree ? (
                  <FileTreeNode
                    node={fileTree}
                    depth={0}
                    selectedPath={selectedFile?.path}
                    isSkill={isSkill}
                    onSelectFile={onSelectFile}
                    confirmingPath={confirmingDeletePath}
                    deletingPath={deletingFilePath}
                    deleteErr={fileErr}
                    onAskDelete={setConfirmingDeletePath}
                    onCancelDelete={() => setConfirmingDeletePath(null)}
                    onConfirmDelete={(path) => void confirmDeleteFile(path)}
                  />
                ) : (
                  <div
                    style={{
                      padding: 20,
                      color: "var(--ink-3)",
                      fontSize: 12.5,
                      textAlign: "center",
                    }}
                  >
                    暂无文件
                  </div>
                )}
              </div>
            </div>

            {/* 右侧内容编辑器 */}
            <div
              style={{
                flex: 1,
                overflow: "auto",
                padding: 16,
                display: "flex",
                flexDirection: "column",
                gap: 12,
                minWidth: 0,
              }}
            >
              {selectedFile ? (
                <>
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      gap: 8,
                    }}
                  >
                    <div
                      style={{
                        fontSize: 12.5,
                        fontWeight: 500,
                        color: "var(--ink)",
                        fontFamily: "var(--mono)",
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                      }}
                    >
                      {selectedFile.path}
                    </div>
                    {isSkill && (
                      <Btn
                        variant="primary"
                        size="sm"
                        icon={saveSuccess ? undefined : <I.Check size={12} />}
                        onClick={onSaveFile}
                        disabled={savingFile}
                        style={
                          saveSuccess
                            ? {
                                background: "var(--success)",
                                borderColor: "var(--success)",
                                color: "#fff",
                              }
                            : undefined
                        }
                      >
                        {savingFile
                          ? "保存中…"
                          : saveSuccess
                            ? "保存成功"
                            : "保存"}
                      </Btn>
                    )}
                  </div>
                  <TextArea
                    value={fileContent}
                    onChange={(e) => onFileContentChange(e.target.value)}
                    disabled={!isSkill}
                    style={{
                      flex: 1,
                      minHeight: 200,
                      fontFamily: "var(--mono)",
                      fontSize: 13,
                      lineHeight: 1.6,
                      resize: "none",
                    }}
                    containerStyle={{ flex: 1, display: "flex", flexDirection: "column" }}
                  />
                </>
              ) : (
                <div
                  style={{
                    flex: 1,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    color: "var(--ink-3)",
                    fontSize: 13,
                  }}
                >
                  请从左侧选择一个文件
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </>
  );
}

// ============ 文件树节点 ============
function FileTreeNode({
  node,
  depth,
  selectedPath,
  isSkill,
  onSelectFile,
  confirmingPath,
  deletingPath,
  deleteErr,
  onAskDelete,
  onCancelDelete,
  onConfirmDelete,
}: {
  node: FileNode;
  depth: number;
  selectedPath?: string;
  isSkill: boolean;
  onSelectFile: (path: string) => void;
  confirmingPath: string | null;
  deletingPath: string | null;
  deleteErr: string | null;
  onAskDelete: (path: string) => void;
  onCancelDelete: () => void;
  onConfirmDelete: (path: string) => void;
}) {
  const isDir = node.type === "dir";
  const [expanded, setExpanded] = useState(depth === 0);
  const [hovered, setHovered] = useState(false);
  const indent = 8 + depth * 14;
  const isSelected = selectedPath === node.path;
  const isConfirming = confirmingPath === node.path;
  const isDeleting = deletingPath === node.path;
  const showDeleteAction = isSkill && !isDir && (hovered || isConfirming || isDeleting);

  return (
    <>
      <div
        onClick={() => {
          if (isDir) {
            setExpanded((v) => !v);
          } else {
            onSelectFile(node.path);
          }
        }}
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
        style={{
          display: "flex",
          alignItems: "center",
          gap: 6,
          padding: "4px 8px",
          paddingLeft: indent,
          fontSize: 13,
          color: isSelected ? "var(--accent)" : "var(--ink)",
          cursor: isDir ? "pointer" : "default",
          borderRadius: 6,
          userSelect: "none",
          background: isSelected
            ? "var(--accent-soft)"
            : hovered || isConfirming
              ? "var(--bg-3)"
              : "transparent",
          transition: "background 120ms",
        }}
      >
        {/* chevron */}
        <span
          style={{
            width: 12,
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            color: "var(--ink-3)",
            flexShrink: 0,
          }}
        >
          {isDir ? (
            expanded ? (
              <I.ChevronDown size={11} />
            ) : (
              <I.ChevronRight size={11} />
            )
          ) : null}
        </span>
        {/* icon */}
        <span
          style={{
            display: "inline-flex",
            alignItems: "center",
            color: isDir
              ? "var(--accent)"
              : isSelected
                ? "var(--accent)"
                : "var(--ink-3)",
            flexShrink: 0,
          }}
        >
          {isDir ? (
            expanded ? (
              <I.FolderOpen size={13} />
            ) : (
              <I.Folder size={13} />
            )
          ) : (
            <I.File size={13} />
          )}
        </span>
        {/* name */}
        <span
          style={{
            flex: 1,
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          {node.name}
        </span>
        {/* 悬停删除按钮(仅技能文件) */}
        {showDeleteAction && (
          <button
            onClick={(e) => {
              e.stopPropagation();
              if (isConfirming) onCancelDelete();
              else onAskDelete(node.path);
            }}
            title="删除文件"
            disabled={isDeleting}
            style={{
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              width: 20,
              height: 20,
              background: isConfirming ? "var(--danger-soft)" : "transparent",
              border: "none",
              color: isConfirming ? "var(--danger)" : "var(--ink-3)",
              cursor: isDeleting ? "default" : "pointer",
              borderRadius: 4,
              opacity: isDeleting ? 0.5 : 1,
            }}
            onMouseEnter={(e) => {
              if (isDeleting) return;
              if (!isConfirming) {
                e.currentTarget.style.background = "var(--danger-soft)";
                e.currentTarget.style.color = "var(--danger)";
              }
            }}
            onMouseLeave={(e) => {
              if (!isConfirming) {
                e.currentTarget.style.background = "transparent";
                e.currentTarget.style.color = "var(--ink-3)";
              }
            }}
          >
            <I.Trash size={11} />
          </button>
        )}
      </div>
      {isConfirming && (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 6,
            padding: "6px 10px",
            margin: "2px 4px 4px",
            background: "var(--danger-soft)",
            border: "1px solid var(--danger)",
            borderRadius: 8,
            fontSize: 12.5,
            color: "var(--danger)",
          }}
        >
          <I.CircleAlert size={12} style={{ flexShrink: 0 }} />
          <span
            style={{
              flex: 1,
              minWidth: 0,
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
          >
            {deleteErr || "确认删除该文件?"}
          </span>
          <button
            onClick={(e) => {
              e.stopPropagation();
              onCancelDelete();
            }}
            disabled={isDeleting}
            style={{
              padding: "3px 10px",
              fontSize: 12,
              background: "transparent",
              border: "1px solid var(--line)",
              borderRadius: 6,
              color: "var(--ink-2)",
              cursor: isDeleting ? "default" : "pointer",
              fontFamily: "inherit",
              flexShrink: 0,
            }}
          >
            取消
          </button>
          <button
            onClick={(e) => {
              e.stopPropagation();
              onConfirmDelete(node.path);
            }}
            disabled={isDeleting}
            style={{
              padding: "3px 10px",
              fontSize: 12,
              background: "var(--danger)",
              border: "1px solid var(--danger)",
              borderRadius: 6,
              color: "#fff",
              cursor: isDeleting ? "default" : "pointer",
              opacity: isDeleting ? 0.6 : 1,
              fontFamily: "inherit",
              display: "inline-flex",
              alignItems: "center",
              gap: 4,
              flexShrink: 0,
            }}
          >
            {isDeleting && <I.Loader size={11} />}
            {isDeleting ? "删除中…" : "删除"}
          </button>
        </div>
      )}
      {expanded &&
        node.children &&
        node.children.map((c) => (
          <FileTreeNode
            key={c.path}
            node={c}
            depth={depth + 1}
            selectedPath={selectedPath}
            isSkill={isSkill}
            onSelectFile={onSelectFile}
            confirmingPath={confirmingPath}
            deletingPath={deletingPath}
            deleteErr={deleteErr}
            onAskDelete={onAskDelete}
            onCancelDelete={onCancelDelete}
            onConfirmDelete={onConfirmDelete}
          />
        ))}
    </>
  );
}

// ============ 空状态 ============
function EmptyState({
  searched,
  type,
  onUpload,
}: {
  searched: boolean;
  type: TabKey;
  onUpload: () => void;
}) {
  return (
    <div
      style={{
        padding: "60px 20px",
        textAlign: "center",
        color: "var(--ink-3)",
      }}
    >
      <div
        style={{
          width: 56,
          height: 56,
          borderRadius: 14,
          background: "var(--accent-soft)",
          color: "var(--accent)",
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "center",
          marginBottom: 12,
        }}
      >
        {type === "skills" ? (
          <I.Sparkles size={28} />
        ) : type === "plugins" ? (
          <I.Puzzle size={28} />
        ) : (
          <I.FolderOpen size={28} />
        )}
      </div>
      <div
        style={{
          fontFamily: "var(--serif)",
          fontSize: 17,
          color: "var(--ink)",
          marginBottom: 4,
        }}
      >
        {searched
          ? "没有匹配的结果"
          : type === "skills"
            ? "还没有上传任何技能"
            : type === "plugins"
              ? "还没有上传任何插件"
              : "还没有创建任何分类"}
      </div>
      <div style={{ fontSize: 13, marginBottom: 16 }}>
        {searched
          ? "试试更换关键词或清空搜索"
          : type === "skills"
            ? "上传一个技能 ZIP 包来开始使用"
            : type === "plugins"
              ? "上传一个插件 ZIP 包来开始使用"
              : "创建一个分类来开始整理"}
      </div>
      {!searched && (
        <Btn variant="primary" icon={<I.Upload size={14} />} onClick={onUpload}>
          上传 ZIP
        </Btn>
      )}
    </div>
  );
}

// ============ 工具函数 ============
function findFirstFile(node: FileNode): string | null {
  if (node.type === "file") return node.path;
  if (!node.children) return null;
  for (const c of node.children) {
    const found = findFirstFile(c);
    if (found) return found;
  }
  return null;
}

// ============ 样式常量 ============
const iconBtnStyle = {
  background: "transparent",
  border: "1px solid transparent",
  color: "var(--ink-3)",
  cursor: "pointer",
  width: 28,
  height: 28,
  borderRadius: 6,
  display: "inline-flex",
  alignItems: "center",
  justifyContent: "center",
  transition: "background 120ms, color 120ms",
} as const;

const smallBtnStyle = {
  display: "inline-flex",
  alignItems: "center",
  justifyContent: "center",
  gap: 4,
  padding: "4px 8px",
  fontSize: 12,
  background: "transparent",
  border: "1px solid var(--line)",
  borderRadius: 6,
  color: "var(--ink-3)",
  cursor: "pointer",
  transition: "background 120ms, color 120ms",
} as const;

// ============ 分组列表 ============
function GroupedItemList({
  groups,
  type,
  categories,
  savingCategoryKey,
  onEdit,
  onDelete,
  onCategoryChange,
}: {
  groups: { category: string; items: (Skill | Plugin)[] }[];
  type: "skill" | "plugin";
  categories: Category[];
  savingCategoryKey: string | null;
  onEdit: (name: string, type: "skill" | "plugin") => void;
  onDelete: (name: string, type: "skill" | "plugin") => void;
  onCategoryChange: (
    type: "skill" | "plugin",
    key: string,
    categoryId: number,
  ) => void;
}) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
      {groups.map(({ category, items }) => (
        <div key={category}>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 8,
              marginBottom: 12,
              paddingBottom: 8,
              borderBottom: "1px solid var(--line)",
            }}
          >
            <span
              style={{
                fontSize: 14,
                fontWeight: 600,
                color: "var(--ink)",
              }}
            >
              {category}
            </span>
            <span
              style={{
                fontSize: 12,
                color: "var(--ink-3)",
                background: "var(--bg-2)",
                padding: "2px 8px",
                borderRadius: 999,
              }}
            >
              {items.length}
            </span>
          </div>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))",
              gap: 12,
            }}
          >
            {items.map((item) => {
              const name =
                type === "skill"
                  ? (item as Skill).name
                  : (item as Plugin).name;
              const desc =
                type === "skill"
                  ? (item as Skill).description
                  : (item as Plugin).description;
              const itemCategory =
                type === "skill"
                  ? (item as Skill).category
                  : (item as Plugin).category;
              const categoryKey =
                type === "skill"
                  ? (item as Skill).name
                  : (item as Plugin).path;
              return (
                <ItemCard
                  key={name}
                  name={name}
                  description={desc}
                  fileCount={0}
                  type={type}
                  category={itemCategory}
                  categories={categories}
                  savingCategory={savingCategoryKey === `${type}:${categoryKey}`}
                  onEdit={() => onEdit(name, type)}
                  onDelete={() => onDelete(name, type)}
                  onCategoryChange={(categoryId) =>
                    onCategoryChange(type, categoryKey, categoryId)
                  }
                />
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}

// ============ 分类管理 ============
function CategoryManager({
  categories,
  newCategoryName,
  setNewCategoryName,
  creatingCategory,
  onCreateCategory,
  renamingCategory,
  setRenamingCategory,
  renameValue,
  setRenameValue,
  onRenameCategory,
  deletingCategoryId,
  setDeletingCategoryId,
  onDeleteCategory,
}: {
  categories: Category[];
  newCategoryName: string;
  setNewCategoryName: (v: string) => void;
  creatingCategory: boolean;
  onCreateCategory: () => void;
  renamingCategory: Category | null;
  setRenamingCategory: (v: Category | null) => void;
  renameValue: string;
  setRenameValue: (v: string) => void;
  onRenameCategory: () => void;
  deletingCategoryId: number | null;
  setDeletingCategoryId: (v: number | null) => void;
  onDeleteCategory: () => void;
}) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {/* 新建分类 */}
      <div
        style={{
          display: "flex",
          gap: 8,
          alignItems: "center",
        }}
      >
        <Input
          placeholder="新分类名称"
          value={newCategoryName}
          onChange={(e) => setNewCategoryName(e.target.value)}
          containerStyle={{ width: 240 }}
          onKeyDown={(e) => {
            if (e.key === "Enter") onCreateCategory();
          }}
        />
        <Btn
          variant="primary"
          onClick={onCreateCategory}
          disabled={creatingCategory || !newCategoryName.trim()}
        >
          {creatingCategory ? "创建中…" : "新建分类"}
        </Btn>
      </div>

      {/* 分类列表 */}
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          gap: 8,
        }}
      >
        {categories.map((cat) => (
          <div
            key={cat.id}
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              padding: "12px 16px",
              background: "var(--bg-2)",
              borderRadius: 8,
              border: "1px solid var(--line)",
            }}
          >
            {renamingCategory?.id === cat.id ? (
              <div style={{ display: "flex", gap: 8, flex: 1 }}>
                <Input
                  value={renameValue}
                  onChange={(e) => setRenameValue(e.target.value)}
                  autoFocus
                  onKeyDown={(e) => {
                    if (e.key === "Enter") onRenameCategory();
                    if (e.key === "Escape") setRenamingCategory(null);
                  }}
                />
                <Btn variant="ghost" onClick={() => setRenamingCategory(null)}>
                  取消
                </Btn>
                <Btn variant="primary" onClick={onRenameCategory}>
                  确认
                </Btn>
              </div>
            ) : (
              <>
                <span style={{ fontSize: 14, fontWeight: 500, color: "var(--ink)" }}>
                  {cat.name}
                </span>
                <div style={{ display: "flex", gap: 4 }}>
                  <button
                    onClick={() => {
                      setRenamingCategory(cat);
                      setRenameValue(cat.name);
                    }}
                    className="focus-ring"
                    style={iconBtnStyle}
                  >
                    <I.Edit size={14} />
                  </button>
                  {cat.name !== "默认" && (
                    <>
                      <button
                        onClick={() => setDeletingCategoryId(cat.id)}
                        className="focus-ring"
                        style={{
                          ...iconBtnStyle,
                          color: "var(--danger)",
                        }}
                      >
                        <I.Trash size={14} />
                      </button>
                    </>
                  )}
                </div>
              </>
            )}
            {deletingCategoryId === cat.id && (
              <div
                style={{
                  position: "fixed",
                  inset: 0,
                  zIndex: 60,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  padding: 24,
                }}
              >
                <div
                  onClick={() => setDeletingCategoryId(null)}
                  style={{
                    position: "fixed",
                    inset: 0,
                    background: "rgba(0,0,0,0.32)",
                    zIndex: 60,
                  }}
                />
                <div
                  style={{
                    position: "relative",
                    zIndex: 61,
                    background: "var(--bg)",
                    border: "1px solid var(--line)",
                    borderRadius: 12,
                    boxShadow: "var(--shadow-lg)",
                    padding: "20px 20px 16px",
                    width: "min(360px, 100%)",
                    display: "flex",
                    flexDirection: "column",
                    gap: 14,
                  }}
                >
                  <h3
                    style={{
                      fontFamily: "var(--serif)",
                      fontSize: 16,
                      fontWeight: 500,
                      color: "var(--ink)",
                      margin: 0,
                    }}
                  >
                    确认删除分类
                  </h3>
                  <p style={{ fontSize: 13, color: "var(--ink-2)", margin: 0 }}>
                    删除后，该分类下的技能和插件将自动移动到默认分类。
                  </p>
                  <div
                    style={{
                      display: "flex",
                      justifyContent: "flex-end",
                      gap: 8,
                    }}
                  >
                    <Btn
                      variant="ghost"
                      onClick={() => setDeletingCategoryId(null)}
                    >
                      取消
                    </Btn>
                    <Btn variant="danger" onClick={onDeleteCategory}>
                      删除
                    </Btn>
                  </div>
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
