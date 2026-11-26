import icon from "./icon.png";
import { AlignLeft, AudioLines, Table2 } from "lucide-react";

export function Mark() {
  return <span className="mark" aria-hidden="true"><img src={icon.src} alt="" draggable={false} /></span>;
}

export function SourceArt() {
  return <div className="source-art" aria-hidden="true">
    <div className="art-grid" />
    <div className="folio-objects">
      <div className="sheet sheet-back"><AudioLines /><span className="wave-bars">{[12,24,17,32,13,21,10,28,15,22,10].map((h,i) => <i key={i} style={{height:h}} />)}</span></div>
      <div className="sheet sheet-middle"><Table2 /><div className="table-pattern" /></div>
      <div className="sheet sheet-front"><AlignLeft /><div className="page-heading" /><div className="page-rule" /><div className="page-rule short" /><i className="index-tab" /></div>
      <div className="folder-face"><Mark /></div>
    </div>
  </div>;
}
