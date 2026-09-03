import antigenDendriticCell from "./antigen-dendritic-cell.png";
import antigenVirus from "./antigen-virus.png";
import dendriticArms from "./antigen-capture/dendritic-arms.png";
import dendriticGrabReady from "./antigen-capture/dendritic-grab-ready.png";
import dendriticSatisfied from "./antigen-capture/dendritic-satisfied.png";
import dendriticSideArms from "./antigen-capture/dendritic-side-arms.png";
import dendriticSideHolding from "./antigen-capture/dendritic-side-holding.png";
import dendriticSideSatisfied from "./antigen-capture/dendritic-side-satisfied.png";
import dendriticSideSwallow from "./antigen-capture/dendritic-side-swallow.png";
import dendriticCaptureArmLowerV2 from "./antigen-capture/dendritic-capture-arm-lower-v2.png";
import dendriticCaptureArmUpperV2 from "./antigen-capture/dendritic-capture-arm-upper-v2.png";
import dendriticCaptureStrainedV2 from "./antigen-capture/dendritic-capture-strained-v2.png";
import dendriticCaptureSwallowV2 from "./antigen-capture/dendritic-capture-swallow-v2.png";
import dendriticStrained from "./antigen-capture/dendritic-strained.png";
import dendriticSwallow from "./antigen-capture/dendritic-swallow.png";
import antigenVirusStruggleCenterV2 from "./antigen-capture/antigen-virus-struggle-center-v2.png";
import antigenVirusStruggleLeftV2 from "./antigen-capture/antigen-virus-struggle-left-v2.png";
import antigenVirusStruggleRightV2 from "./antigen-capture/antigen-virus-struggle-right-v2.png";
import antigenVirusSwallowV2 from "./antigen-capture/antigen-virus-swallow-v2.png";
import dendriticCell from "./dendritic-cell.svg";
import injectionNeedle from "./injection-needle.png";
import injectionSkin from "./injection-skin.png";
import injectionVirus from "./injection-virus.png";
import mazeDendriticCell from "./maze-dendritic-cell.png";
import mazeVirus from "./maze-virus.png";
import macrophage from "./macrophage.svg";
import tissueBackground from "./tissue-background.png";
import virus from "./virus.png";

export const immuneAssets = {
  antigenDendriticCell,
  antigenVirus,
  dendriticGrabReady,
  dendriticStrained,
  dendriticSwallow,
  dendriticSatisfied,
  dendriticArms,
  dendriticSideHolding,
  dendriticSideSwallow,
  dendriticSideSatisfied,
  dendriticSideArms,
  dendriticCaptureArmUpperV2,
  dendriticCaptureArmLowerV2,
  dendriticCaptureStrainedV2,
  dendriticCaptureSwallowV2,
  antigenVirusStruggleLeftV2,
  antigenVirusStruggleCenterV2,
  antigenVirusStruggleRightV2,
  antigenVirusSwallowV2,
  virusNeutral: virus,
  virusExploring: mazeVirus,
  virusNervous: virus,
  injectionVirus,
  tissueBackground,
  skinLayer: injectionSkin,
  needle: injectionNeedle,
  dendriticCell,
  mazeDendriticCell,
  macrophage,
} as const;
