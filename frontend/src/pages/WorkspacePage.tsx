import WorkspaceFileManager from "@/components/workspace/WorkspaceFileManager";
import { personalWorkspaceApi } from "@/lib/workspaceApi";

const personalApi = personalWorkspaceApi();

interface Props {
  onOpenSessions?: () => void;
}

export default function WorkspacePage({ onOpenSessions }: Props) {
  return (
    <WorkspaceFileManager
      title="个人空间"
      api={personalApi}
      onOpenSessions={onOpenSessions}
    />
  );
}
