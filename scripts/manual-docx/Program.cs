using DocumentFormat.OpenXml;
using DocumentFormat.OpenXml.Packaging;
using DocumentFormat.OpenXml.Validation;
using DocumentFormat.OpenXml.Wordprocessing;
using Markdig;
using Markdig.Extensions.Tables;
using Markdig.Syntax;
using Markdig.Syntax.Inlines;
using A = DocumentFormat.OpenXml.Drawing;
using DW = DocumentFormat.OpenXml.Drawing.Wordprocessing;
using PIC = DocumentFormat.OpenXml.Drawing.Pictures;
using WTable = DocumentFormat.OpenXml.Wordprocessing.Table;
using WTableCell = DocumentFormat.OpenXml.Wordprocessing.TableCell;
using WTableRow = DocumentFormat.OpenXml.Wordprocessing.TableRow;
using MdTable = Markdig.Extensions.Tables.Table;
using MdTableCell = Markdig.Extensions.Tables.TableCell;
using MdTableRow = Markdig.Extensions.Tables.TableRow;

const string Accent = "24745B";
const string AccentDark = "1C604A";
const string Text = "28332D";
const string Muted = "69766F";
const string Line = "DDE5E0";
const string Soft = "EEF5F1";

var root = Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "..", "..", "..", "..", ".."));
var output = Path.Combine(root, "docs", "多智能体课程教学设计平台_开发记录与用户使用手册_2026-08-02.docx");
var devLog = File.ReadAllText(Path.Combine(root, "docs", "今日开发记录_2026-08-02.md"));
var manual = File.ReadAllText(Path.Combine(root, "docs", "用户使用手册.md"));
var processShot = Path.Combine(root, ".runtime", "browser-check", "screenshots", "desktop-process.png");
var materialShot = Path.Combine(root, ".runtime", "browser-check", "screenshots", "desktop-real-book.png");

Directory.CreateDirectory(Path.GetDirectoryName(output)!);
if (File.Exists(output)) File.Delete(output);

using var document = WordprocessingDocument.Create(output, WordprocessingDocumentType.Document);
var main = document.AddMainDocumentPart();
main.Document = new Document(new Body());
var body = main.Document.Body!;

AddStyles(main);
AddSettings(main);
AddCoreProperties(document);
var headerId = AddHeader(main);
var footerId = AddFooter(main);

AddCover(body);
AddToc(body);
body.Append(PageBreak());

body.Append(Heading("第一部分  今日开发记录", 1));
RenderMarkdown(body, StripFirstHeading(devLog));
body.Append(PageBreak());

body.Append(Heading("第二部分  用户使用手册", 1));
RenderMarkdown(body, StripFirstHeading(manual));

body.Append(Heading("界面示例", 1));
if (File.Exists(processShot)) {
    body.Append(Caption("图 1  生成过程：全局阶段与局部轮次视图"));
    body.Append(ImageParagraph(main, processShot, 6.3, 3.94, 1U, "生成过程界面"));
}
if (File.Exists(materialShot)) {
    body.Append(Caption("图 2  真实课本：解析质量、目录与原文预览"));
    body.Append(ImageParagraph(main, materialShot, 6.3, 3.94, 2U, "材料预览界面"));
}

var section = new SectionProperties(
    new HeaderReference { Type = HeaderFooterValues.Default, Id = headerId },
    new FooterReference { Type = HeaderFooterValues.Default, Id = footerId },
    new PageSize { Width = 11906U, Height = 16838U },
    new PageMargin { Top = 1134, Right = 1134U, Bottom = 1134, Left = 1134U, Header = 567U, Footer = 567U, Gutter = 0U });
body.Append(section);
main.Document.Save();
document.Dispose();

using (var check = WordprocessingDocument.Open(output, false)) {
    var errors = new OpenXmlValidator(FileFormatVersions.Office2019).Validate(check).ToList();
    if (errors.Count > 0) {
        foreach (var error in errors.Take(20)) Console.Error.WriteLine($"{error.Path?.XPath}: {error.Description}");
        throw new InvalidDataException($"OpenXML validation failed with {errors.Count} error(s).");
    }
    var checkBody = check.MainDocumentPart?.Document.Body ?? throw new InvalidDataException("Document body is missing.");
    var allText = checkBody.InnerText;
    string[] required = ["今日开发记录", "用户使用手册", "113 passed", "创建教学设计", "编辑教学成果", "数据与安全"];
    var missing = required.Where(value => !allText.Contains(value, StringComparison.Ordinal)).ToList();
    if (missing.Count > 0) throw new InvalidDataException($"Missing required content: {string.Join(", ", missing)}");
    if (checkBody.Elements<SectionProperties>().Count() != 1 || checkBody.LastChild is not SectionProperties)
        throw new InvalidDataException("Section properties must be the final body element.");
    if (check.MainDocumentPart!.ImageParts.Count() != 2) throw new InvalidDataException("Expected two screenshots.");
}

Console.WriteLine($"Created and validated: {output}");

static string StripFirstHeading(string markdown) {
    var lines = markdown.Replace("\r\n", "\n").Split('\n').ToList();
    var first = lines.FindIndex(line => line.StartsWith("# "));
    if (first >= 0) lines.RemoveAt(first);
    return string.Join("\n", lines).Trim();
}

static void AddCoreProperties(WordprocessingDocument document) {
    var props = document.PackageProperties;
    props.Title = "多智能体课程教学设计平台开发记录与用户使用手册";
    props.Subject = "教师优先工作台 v2.0";
    props.Creator = "多智能体课程教学设计平台开发组";
    props.Description = "2026-08-02 开发记录、当前功能说明和教师用户使用手册";
    props.Created = new DateTime(2026, 8, 2);
}

static void AddSettings(MainDocumentPart main) {
    var part = main.AddNewPart<DocumentSettingsPart>();
    part.Settings = new Settings(
        new Compatibility(new CompatibilitySetting { Name = CompatSettingNameValues.CompatibilityMode, Uri = "http://schemas.microsoft.com/office/word", Val = "15" }));
    part.Settings.Save();
}

static void AddStyles(MainDocumentPart main) {
    var part = main.AddNewPart<StyleDefinitionsPart>();
    var styles = new Styles(
        new DocDefaults(
            new RunPropertiesDefault(new RunPropertiesBaseStyle(
                new RunFonts { Ascii = "Aptos", HighAnsi = "Aptos", EastAsia = "Microsoft YaHei" },
                new Color { Val = Text }, new FontSize { Val = "21" }, new FontSizeComplexScript { Val = "21" })),
            new ParagraphPropertiesDefault(new ParagraphPropertiesBaseStyle(
                new SpacingBetweenLines { After = "120", Line = "300", LineRule = LineSpacingRuleValues.Auto }))));

    styles.Append(new Style(
        new StyleName { Val = "Normal" },
        new StyleParagraphProperties(new SpacingBetweenLines { After = "120", Line = "300", LineRule = LineSpacingRuleValues.Auto }),
        new StyleRunProperties(new RunFonts { Ascii = "Aptos", HighAnsi = "Aptos", EastAsia = "Microsoft YaHei" }, new Color { Val = Text }, new FontSize { Val = "21" }))
    { Type = StyleValues.Paragraph, StyleId = "Normal", Default = true });

    styles.Append(new Style(
        new StyleName { Val = "Title" }, new BasedOn { Val = "Normal" },
        new StyleParagraphProperties(new SpacingBetweenLines { Before = "1200", After = "260" }, new Justification { Val = JustificationValues.Center }),
        new StyleRunProperties(new RunFonts { EastAsia = "Microsoft YaHei", Ascii = "Aptos Display", HighAnsi = "Aptos Display" }, new Bold(), new Color { Val = AccentDark }, new FontSize { Val = "48" }))
    { Type = StyleValues.Paragraph, StyleId = "Title" });

    styles.Append(new Style(
        new StyleName { Val = "Subtitle" }, new BasedOn { Val = "Normal" },
        new StyleParagraphProperties(new SpacingBetweenLines { After = "180" }, new Justification { Val = JustificationValues.Center }),
        new StyleRunProperties(new RunFonts { EastAsia = "Microsoft YaHei" }, new Color { Val = Muted }, new FontSize { Val = "24" }))
    { Type = StyleValues.Paragraph, StyleId = "Subtitle" });

    string[] sizes = ["34", "28", "24", "22"];
    string[] colors = [AccentDark, Accent, Text, Text];
    for (var i = 0; i < sizes.Length; i++) {
        styles.Append(new Style(
            new StyleName { Val = $"heading {i + 1}" }, new BasedOn { Val = "Normal" }, new NextParagraphStyle { Val = "Normal" }, new PrimaryStyle(),
            new StyleParagraphProperties(new KeepNext(), new KeepLines(), new SpacingBetweenLines { Before = i == 0 ? "400" : "280", After = "120" }, new OutlineLevel { Val = i }),
            new StyleRunProperties(new RunFonts { EastAsia = "Microsoft YaHei", Ascii = "Aptos Display", HighAnsi = "Aptos Display" }, new Bold(), new Color { Val = colors[i] }, new FontSize { Val = sizes[i] }))
        { Type = StyleValues.Paragraph, StyleId = $"Heading{i + 1}" });
    }

    styles.Append(new Style(
        new StyleName { Val = "Caption" }, new BasedOn { Val = "Normal" },
        new StyleParagraphProperties(new KeepNext(), new SpacingBetweenLines { Before = "160", After = "80" }, new Justification { Val = JustificationValues.Center }),
        new StyleRunProperties(new Color { Val = Muted }, new FontSize { Val = "18" }))
    { Type = StyleValues.Paragraph, StyleId = "Caption" });
    part.Styles = styles;
    part.Styles.Save();
}

static string AddHeader(MainDocumentPart main) {
    var part = main.AddNewPart<HeaderPart>();
    var paragraph = new Paragraph(
        new ParagraphProperties(
            new ParagraphBorders(new BottomBorder { Val = BorderValues.Single, Size = 6U, Space = 5U, Color = Line }),
            new SpacingBetweenLines { After = "80" },
            new Justification { Val = JustificationValues.Right }),
        new Run(new RunProperties(new Color { Val = Muted }, new FontSize { Val = "17" }), new Text("课程教学智能体平台 · 教师优先工作台")));
    part.Header = new Header(paragraph);
    part.Header.Save();
    return main.GetIdOfPart(part);
}

static string AddFooter(MainDocumentPart main) {
    var part = main.AddNewPart<FooterPart>();
    var paragraph = new Paragraph(new ParagraphProperties(new Justification { Val = JustificationValues.Center }));
    paragraph.Append(new Run(new RunProperties(new Color { Val = Muted }, new FontSize { Val = "18" }), new Text("- ") { Space = SpaceProcessingModeValues.Preserve }));
    paragraph.Append(new Run(new FieldChar { FieldCharType = FieldCharValues.Begin }));
    paragraph.Append(new Run(new FieldCode(" PAGE ") { Space = SpaceProcessingModeValues.Preserve }));
    paragraph.Append(new Run(new FieldChar { FieldCharType = FieldCharValues.Separate }));
    paragraph.Append(new Run(new Text("1")));
    paragraph.Append(new Run(new FieldChar { FieldCharType = FieldCharValues.End }));
    paragraph.Append(new Run(new RunProperties(new Color { Val = Muted }, new FontSize { Val = "18" }), new Text(" -") { Space = SpaceProcessingModeValues.Preserve }));
    part.Footer = new Footer(paragraph);
    part.Footer.Save();
    return main.GetIdOfPart(part);
}

static void AddCover(Body body) {
    body.Append(new Paragraph(new ParagraphProperties(new SpacingBetweenLines { Before = "900", After = "160" }, new Justification { Val = JustificationValues.Center }),
        new Run(new RunProperties(new Bold(), new Color { Val = Accent }, new FontSize { Val = "22" }), new Text("MULTI-AGENT TEACHING STUDIO"))));
    body.Append(new Paragraph(new ParagraphProperties(new ParagraphStyleId { Val = "Title" }), new Run(new Text("多智能体课程教学设计平台"))));
    body.Append(new Paragraph(new ParagraphProperties(new ParagraphStyleId { Val = "Title" }, new SpacingBetweenLines { After = "360" }), new Run(new Text("开发记录与用户使用手册"))));
    body.Append(new Paragraph(new ParagraphProperties(new ParagraphStyleId { Val = "Subtitle" }), new Run(new Text("教师优先工作台 · v2.0"))));
    body.Append(InfoBox("文档内容", "第一部分记录 2026-08-02 的开发交付、问题修复与验收结果；第二部分说明教师从材料上传到成果审核与导出的完整操作。"));
    body.Append(new Paragraph(new ParagraphProperties(new SpacingBetweenLines { Before = "1100", After = "100" }, new Justification { Val = JustificationValues.Center }),
        new Run(new RunProperties(new Color { Val = Muted }, new FontSize { Val = "21" }), new Text("更新日期：2026 年 8 月 2 日"))));
    body.Append(new Paragraph(new ParagraphProperties(new Justification { Val = JustificationValues.Center }),
        new Run(new RunProperties(new Color { Val = Muted }, new FontSize { Val = "21" }), new Text("适用对象：任课教师、课程负责人、教学设计人员、平台管理员"))));
    body.Append(PageBreak());
}

static void AddToc(Body body) {
    body.Append(Heading("目录", 1));
    var paragraph = new Paragraph();
    paragraph.Append(new Run(new FieldChar { FieldCharType = FieldCharValues.Begin }));
    paragraph.Append(new Run(new FieldCode(" TOC \\o \"1-3\" \\h \\z \\u ") { Space = SpaceProcessingModeValues.Preserve }));
    paragraph.Append(new Run(new FieldChar { FieldCharType = FieldCharValues.Separate }));
    paragraph.Append(new Run(new RunProperties(new Color { Val = Muted }), new Text("请在 Word 中选中目录并按 F9 生成或更新页码。")));
    paragraph.Append(new Run(new FieldChar { FieldCharType = FieldCharValues.End }));
    body.Append(paragraph);
}

static WTable InfoBox(string title, string content) {
    var table = new WTable(
        new TableProperties(
            new TableWidth { Width = "5000", Type = TableWidthUnitValues.Pct },
            new TableBorders(new TopBorder { Val = BorderValues.Single, Size = 6U, Color = "B8D1C5" }, new LeftBorder { Val = BorderValues.Single, Size = 6U, Color = "B8D1C5" }, new BottomBorder { Val = BorderValues.Single, Size = 6U, Color = "B8D1C5" }, new RightBorder { Val = BorderValues.Single, Size = 6U, Color = "B8D1C5" }),
            new TableCellMarginDefault(new TopMargin { Width = "140", Type = TableWidthUnitValues.Dxa }, new TableCellLeftMargin { Width = 180, Type = TableWidthValues.Dxa }, new BottomMargin { Width = "140", Type = TableWidthUnitValues.Dxa }, new TableCellRightMargin { Width = 180, Type = TableWidthValues.Dxa })),
        new TableGrid(new GridColumn { Width = "9500" }));
    var cell = new WTableCell(
        new TableCellProperties(new TableCellWidth { Width = "9500", Type = TableWidthUnitValues.Dxa }, new Shading { Val = ShadingPatternValues.Clear, Fill = Soft }),
        new Paragraph(new Run(new RunProperties(new Bold(), new Color { Val = AccentDark }), new Text(title))),
        new Paragraph(new Run(new Text(content))));
    table.Append(new WTableRow(cell));
    return table;
}

static Paragraph Heading(string text, int level) => new(
    new ParagraphProperties(new ParagraphStyleId { Val = $"Heading{Math.Clamp(level, 1, 4)}" }),
    new Run(new Text(text)));

static Paragraph Caption(string text) => new(
    new ParagraphProperties(new ParagraphStyleId { Val = "Caption" }), new Run(new Text(text)));

static Paragraph PageBreak() => new(new Run(new Break { Type = BreakValues.Page }));

static void RenderMarkdown(Body body, string markdown) {
    var pipeline = new MarkdownPipelineBuilder().UsePipeTables().Build();
    var doc = Markdown.Parse(markdown, pipeline);
    foreach (var block in doc) RenderBlock(body, block, 0);
}

static void RenderBlock(OpenXmlCompositeElement parent, Block block, int listDepth) {
    switch (block) {
        case HeadingBlock heading:
            var hp = Heading(string.Empty, heading.Level);
            AppendInlines(hp, heading.Inline);
            parent.Append(hp);
            break;
        case ParagraphBlock paragraph:
            var p = new Paragraph();
            AppendInlines(p, paragraph.Inline);
            parent.Append(p);
            break;
        case ListBlock list:
            var index = 1;
            foreach (var child in list) {
                if (child is not ListItemBlock item) continue;
                foreach (var itemBlock in item) {
                    if (itemBlock is ParagraphBlock itemParagraph) {
                        var marker = list.IsOrdered ? $"{index}. " : "• ";
                        var lp = new Paragraph(new ParagraphProperties(new SpacingBetweenLines { After = "50" }, new Indentation { Left = (360 * (listDepth + 1)).ToString(), Hanging = "260" }), new Run(new Text(marker) { Space = SpaceProcessingModeValues.Preserve }));
                        AppendInlines(lp, itemParagraph.Inline);
                        parent.Append(lp);
                    } else RenderBlock(parent, itemBlock, listDepth + 1);
                }
                index++;
            }
            break;
        case FencedCodeBlock code:
            var cp = new Paragraph(new ParagraphProperties(new Shading { Val = ShadingPatternValues.Clear, Fill = "F3F6F4" }, new SpacingBetweenLines { Before = "80", After = "120", Line = "260", LineRule = LineSpacingRuleValues.Auto }, new Indentation { Left = "240", Right = "240" }));
            cp.Append(new Run(new RunProperties(new RunFonts { Ascii = "Consolas", HighAnsi = "Consolas", EastAsia = "Microsoft YaHei" }, new Color { Val = "314139" }, new FontSize { Val = "18" }), new Text(code.Lines.ToString()) { Space = SpaceProcessingModeValues.Preserve }));
            parent.Append(cp);
            break;
        case MdTable table:
            parent.Append(RenderTable(table));
            break;
        case ThematicBreakBlock:
            parent.Append(new Paragraph(new ParagraphProperties(new ParagraphBorders(new BottomBorder { Val = BorderValues.Single, Size = 4U, Color = Line }), new SpacingBetweenLines { Before = "80", After = "120" })));
            break;
        case ContainerBlock container:
            foreach (var child in container) RenderBlock(parent, child, listDepth);
            break;
    }
}

static void AppendInlines(Paragraph paragraph, ContainerInline? container) {
    if (container is null) return;
    for (var inline = container.FirstChild; inline is not null; inline = inline.NextSibling) AppendInline(paragraph, inline, false, false);
}

static void AppendInline(Paragraph paragraph, Inline inline, bool bold, bool italic) {
    switch (inline) {
        case LiteralInline literal:
            paragraph.Append(TextRun(literal.Content.ToString(), bold, italic, false));
            break;
        case CodeInline code:
            paragraph.Append(TextRun(code.Content, bold, italic, true));
            break;
        case EmphasisInline emphasis:
            for (var child = emphasis.FirstChild; child is not null; child = child.NextSibling)
                AppendInline(paragraph, child, bold || emphasis.DelimiterCount >= 2, italic || emphasis.DelimiterCount == 1);
            break;
        case LineBreakInline:
            paragraph.Append(new Run(new Break()));
            break;
        case LinkInline link:
            if (link.IsImage) break;
            for (var child = link.FirstChild; child is not null; child = child.NextSibling) AppendInline(paragraph, child, bold, italic);
            if (!string.IsNullOrWhiteSpace(link.Url)) paragraph.Append(TextRun($" ({link.Url})", false, false, false, Accent));
            break;
        case ContainerInline nested:
            for (var child = nested.FirstChild; child is not null; child = child.NextSibling) AppendInline(paragraph, child, bold, italic);
            break;
    }
}

static Run TextRun(string text, bool bold, bool italic, bool code, string? color = null) {
    var props = new RunProperties();
    if (code) props.Append(new RunFonts { Ascii = "Consolas", HighAnsi = "Consolas", EastAsia = "Microsoft YaHei" });
    if (bold) props.Append(new Bold());
    if (italic) props.Append(new Italic());
    if (color is not null) props.Append(new Color { Val = color });
    if (code) props.Append(new FontSize { Val = "19" }, new Shading { Val = ShadingPatternValues.Clear, Fill = "EFF3F1" });
    return new Run(props, new Text(text) { Space = SpaceProcessingModeValues.Preserve });
}

static WTable RenderTable(MdTable source) {
    var rows = source.OfType<MdTableRow>().ToList();
    var columnCount = Math.Max(1, rows.Select(row => row.Count).DefaultIfEmpty(1).Max());
    var width = 9500 / columnCount;
    var table = new WTable(
        new TableProperties(
            new TableWidth { Width = "5000", Type = TableWidthUnitValues.Pct },
            new TableBorders(new TopBorder { Val = BorderValues.Single, Size = 6U, Color = Line }, new LeftBorder { Val = BorderValues.Single, Size = 4U, Color = Line }, new BottomBorder { Val = BorderValues.Single, Size = 6U, Color = Line }, new RightBorder { Val = BorderValues.Single, Size = 4U, Color = Line }, new InsideHorizontalBorder { Val = BorderValues.Single, Size = 4U, Color = Line }, new InsideVerticalBorder { Val = BorderValues.Single, Size = 4U, Color = Line }),
            new TableLayout { Type = TableLayoutValues.Fixed },
            new TableCellMarginDefault(new TopMargin { Width = "90", Type = TableWidthUnitValues.Dxa }, new TableCellLeftMargin { Width = 110, Type = TableWidthValues.Dxa }, new BottomMargin { Width = "90", Type = TableWidthUnitValues.Dxa }, new TableCellRightMargin { Width = 110, Type = TableWidthValues.Dxa })),
        new TableGrid(Enumerable.Range(0, columnCount).Select(_ => new GridColumn { Width = width.ToString() })));

    for (var rowIndex = 0; rowIndex < rows.Count; rowIndex++) {
        var row = new WTableRow();
        if (rowIndex == 0) row.Append(new TableRowProperties(new TableHeader()));
        foreach (var sourceCell in rows[rowIndex].OfType<MdTableCell>()) {
            var cell = new WTableCell();
            cell.Append(new TableCellProperties(new TableCellWidth { Width = width.ToString(), Type = TableWidthUnitValues.Dxa }, new Shading { Val = ShadingPatternValues.Clear, Fill = rowIndex == 0 ? AccentDark : rowIndex % 2 == 0 ? "F7F9F8" : "FFFFFF" }));
            var paragraph = new Paragraph(new ParagraphProperties(new SpacingBetweenLines { After = "20", Line = "260", LineRule = LineSpacingRuleValues.Auto }));
            foreach (var block in sourceCell) {
                if (block is ParagraphBlock pb) AppendInlines(paragraph, pb.Inline);
            }
            if (rowIndex == 0) {
                foreach (var run in paragraph.Elements<Run>()) {
                    run.RunProperties = new RunProperties(new Bold(), new Color { Val = "FFFFFF" });
                }
            }
            cell.Append(paragraph);
            row.Append(cell);
        }
        table.Append(row);
    }
    return table;
}

static Paragraph ImageParagraph(MainDocumentPart main, string path, double widthInches, double heightInches, uint id, string description) {
    var imagePart = main.AddImagePart(ImagePartType.Png);
    using (var stream = File.OpenRead(path)) imagePart.FeedData(stream);
    var relationshipId = main.GetIdOfPart(imagePart);
    var cx = (long)(widthInches * 914400);
    var cy = (long)(heightInches * 914400);
    var drawing = new Drawing(new DW.Inline(
        new DW.Extent { Cx = cx, Cy = cy },
        new DW.EffectExtent { LeftEdge = 0L, TopEdge = 0L, RightEdge = 0L, BottomEdge = 0L },
        new DW.DocProperties { Id = id, Name = $"Screenshot{id}", Description = description },
        new DW.NonVisualGraphicFrameDrawingProperties(new A.GraphicFrameLocks { NoChangeAspect = true }),
        new A.Graphic(new A.GraphicData(new PIC.Picture(
            new PIC.NonVisualPictureProperties(new PIC.NonVisualDrawingProperties { Id = 0U, Name = Path.GetFileName(path) }, new PIC.NonVisualPictureDrawingProperties()),
            new PIC.BlipFill(new A.Blip { Embed = relationshipId }, new A.Stretch(new A.FillRectangle())),
            new PIC.ShapeProperties(new A.Transform2D(new A.Offset { X = 0L, Y = 0L }, new A.Extents { Cx = cx, Cy = cy }), new A.PresetGeometry(new A.AdjustValueList()) { Preset = A.ShapeTypeValues.Rectangle })))
        { Uri = "http://schemas.openxmlformats.org/drawingml/2006/picture" }))
    { DistanceFromTop = 0U, DistanceFromBottom = 0U, DistanceFromLeft = 0U, DistanceFromRight = 0U });
    return new Paragraph(new ParagraphProperties(new SpacingBetweenLines { After = "160" }, new Justification { Val = JustificationValues.Center }), new Run(drawing));
}
