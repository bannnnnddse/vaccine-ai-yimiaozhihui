import {
  ImmuneExperienceModal,
  type ImmuneExperienceModalProps,
} from "./immune-experience/ImmuneExperienceModal";

export type InteractiveDemoModalProps = ImmuneExperienceModalProps;

export function InteractiveDemoModal(props: InteractiveDemoModalProps) {
  return <ImmuneExperienceModal {...props} />;
}
