/* FolderToMD legacy reader. AGPL-3.0-or-later. Apache POI reads data only.
 * Launched with a restrictive Java 17 security policy: no network or subprocess grants.
 * JSON Lines output avoids any HTML rendering or document-controlled executable content.
 */
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.AccessControlException;
import java.security.AccessController;
import java.net.SocketPermission;
import java.util.*;
import org.apache.poi.hwpf.HWPFDocument;
import org.apache.poi.hwpf.usermodel.*;
import org.apache.poi.hslf.usermodel.*;
import org.apache.poi.hssf.usermodel.HSSFWorkbook;
import org.apache.poi.hssf.usermodel.HSSFPictureData;

public class LegacyReader {
    static PrintWriter out;
    static Set<Integer> pictures = new HashSet<>();
    static String q(String s) {
        if(s==null) return "\"\"";
        StringBuilder b=new StringBuilder("\"");
        for(char c:s.toCharArray()) {
            if(c=='"'||c=='\\') b.append('\\').append(c);
            else if(c=='\n') b.append("\\n");
            else if(c=='\r') b.append("\\r");
            else if(c=='\t') b.append("\\t");
            else if(c<32) b.append(String.format("\\u%04x",(int)c));
            else b.append(c);
        }
        return b.append('"').toString();
    }
    static String clean(String s) { return Range.stripFields(s).replaceAll("[\\x00-\\x08\\x0B\\x0C\\x0E-\\x1F]", "").strip(); }
    static void emit(String kind,String s) {out.println("{\"kind\":"+q(kind)+",\"text\":"+q(s)+"}");}
    static void image(byte[] data,String extension) {
        if(data==null||data.length==0)return;
        int hash=Arrays.hashCode(data);if(!pictures.add(hash))return;
        out.println("{\"kind\":\"image\",\"extension\":"+q(extension)+",\"data\":"+q(Base64.getEncoder().encodeToString(data))+"}");
    }
    static void row(List<String> values) {out.println("{\"kind\":\"row\",\"cells\":["+String.join(",",values.stream().map(LegacyReader::q).toList())+"]}");}
    static void paragraph(Paragraph p,HWPFDocument d) {
        String s=clean(p.text());
        if(!s.isBlank()) {
            String style="";
            try {style=d.getStyleSheet().getStyleDescription(p.getStyleIndex()).getName();} catch(Exception ignored) {}
            emit(style.toLowerCase(Locale.ROOT).startsWith("heading")?"heading":p.isInList()?"list":"text",s);
        }
        for(int i=0;i<p.numCharacterRuns();i++) {
            CharacterRun run=p.getCharacterRun(i);
            if(d.getPicturesTable().hasPicture(run)) {
                Picture pic=d.getPicturesTable().extractPicture(run,true);
                image(pic.getContent(),pic.suggestFileExtension());
            }
        }
    }
    static void range(Range range,HWPFDocument d) {
        int skipUntil=-1;
        for(int i=0;i<range.numParagraphs();i++) {
            Paragraph p=range.getParagraph(i);
            if(p.getStartOffset()<skipUntil)continue;
            if(p.isInTable()) {
                try {
                    Table t=range.getTable(p);emit("table_start","");
                    for(int r=0;r<t.numRows();r++) {
                        TableRow row=t.getRow(r);List<String> cells=new ArrayList<>();
                        for(int c=0;c<row.numCells();c++)cells.add(clean(row.getCell(c).text()));
                        row(cells);
                    }
                    emit("table_end","");skipUntil=t.getEndOffset();
                } catch(Exception e) {paragraph(p,d);emit("warning","Legacy Word table structure could not be fully recovered.");}
            } else paragraph(p,d);
        }
    }
    static void word(Path input) throws Exception {
        try(InputStream stream=Files.newInputStream(input);HWPFDocument d=new HWPFDocument(stream)) {
            range(d.getRange(),d);
            Range[] extra={d.getHeaderStoryRange(),d.getFootnoteRange(),d.getEndnoteRange(),d.getMainTextboxRange()};
            String[] names={"Headers and footers","Footnotes","Endnotes","Text boxes"};
            for(int i=0;i<extra.length;i++)if(extra[i]!=null&&!clean(extra[i].text()).isBlank()){emit("heading",names[i]);range(extra[i],d);}
            for(Picture pic:d.getPicturesTable().getAllPictures())image(pic.getContent(),pic.suggestFileExtension());
            emit("warning","Legacy Word: complex layout, merged tables, field hyperlinks, charts, and OLE objects may not be represented fully. Visible field results retained; active content is never executed.");
        }
    }
    static void shapes(List<HSLFShape> shapes) {
        for(HSLFShape shape:shapes) {
            if(shape instanceof HSLFObjectShape)emit("warning","Embedded OLE object not executed or extracted; a preview may be retained.");
            if(shape instanceof HSLFTable table) {
                emit("table_start","");
                for(int r=0;r<table.getNumberOfRows();r++) {
                    List<String> values=new ArrayList<>();
                    for(int c=0;c<table.getNumberOfColumns();c++){HSLFTableCell cell=table.getCell(r,c);values.add(cell==null?"":cell.getText());}
                    row(values);
                }
                emit("table_end","");
            } else if(shape instanceof HSLFGroupShape group)shapes(group.getShapes());
            else if(shape instanceof HSLFTextShape tx) {
                String s=tx.getText();if(s!=null&&!s.isBlank())emit("text",s);
            } else if(shape instanceof HSLFPictureShape picture) {
                HSLFPictureData data=picture.getPictureData();if(data!=null)image(data.getData(),data.getType().extension);
            } else emit("warning","Legacy slide contains a non-text drawing/shape that is not rendered.");
        }
    }
    static void powerpoint(Path input) throws Exception {
        try(InputStream stream=Files.newInputStream(input);HSLFSlideShow d=new HSLFSlideShow(stream)) {
            int i=0;
            for(HSLFSlide slide:d.getSlides()) {
                emit("slide",Integer.toString(++i));pictures.clear();shapes(slide.getShapes());
                HSLFNotes notes=slide.getNotes();
                if(notes!=null) {
                    emit("heading","Speaker notes");
                    for(List<HSLFTextParagraph> ps:notes.getTextParagraphs())
                        for(HSLFTextParagraph p:ps) {
                            StringBuilder text=new StringBuilder();for(HSLFTextRun run:p.getTextRuns())text.append(run.getRawText());
                            if(!text.toString().isBlank())emit("text",text.toString());
                        }
                }
            }
        }
    }
    static void excelImages(Path input) throws Exception {
        try(InputStream stream=Files.newInputStream(input);HSSFWorkbook d=new HSSFWorkbook(stream)) {
            for(HSSFPictureData p:d.getAllPictures())image(p.getData(),p.suggestFileExtension());
        }
    }
    @SuppressWarnings("removal")
    public static void main(String[] args) throws Exception {
        if(System.getSecurityManager()==null)throw new SecurityException("Offline security policy must be enabled");
        try {AccessController.checkPermission(new SocketPermission("example.com:443","connect,resolve"));throw new SecurityException("Network permission must not be granted");}
        catch(AccessControlException expected) {}
        // Percent-encoded file URIs survive the Windows Java 17 launcher code page.
        Path input=Paths.get(java.net.URI.create(args[0])),output=Paths.get(java.net.URI.create(args[1]));
        System.setProperty("java.io.tmpdir",output.getParent().toString());
        System.setProperty("user.home",output.getParent().toString());
        try(PrintWriter writer=new PrintWriter(Files.newBufferedWriter(output,StandardCharsets.UTF_8))) {
            out=writer;
            if(args[2].equals("doc"))word(input);
            else if(args[2].equals("ppt"))powerpoint(input);
            else if(args[2].equals("xls-images"))excelImages(input);
            else if(args[2].equals("network-test"))emit("text","Network permission denied before parsing");
            else throw new IllegalArgumentException("Unknown reader mode");
        }
    }
}
