import WorkspaceFeature from "../../components/WorkspaceFeature";
import ProtocolUpload from "../../pages/ProtocolUpload";

export default function UploadFeature() {
  return <WorkspaceFeature feature="upload" preview={<ProtocolUpload previewOnly />}><ProtocolUpload /></WorkspaceFeature>;
}
