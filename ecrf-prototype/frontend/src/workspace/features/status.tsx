import WorkspaceFeature from "../../components/WorkspaceFeature";
import EcrfStatus from "../../pages/EcrfStatus";

export default function StatusFeature() {
  return <WorkspaceFeature feature="status" preview={<EcrfStatus previewOnly />}><EcrfStatus /></WorkspaceFeature>;
}
