using DocumentFormat.OpenXml;
using DocumentFormat.OpenXml.Packaging;
using DocumentFormat.OpenXml.Validation;
using DocumentFormat.OpenXml.Wordprocessing;
using A = DocumentFormat.OpenXml.Drawing;
using DW = DocumentFormat.OpenXml.Drawing.Wordprocessing;
using PIC = DocumentFormat.OpenXml.Drawing.Pictures;

if (args.Length != 3)
{
    Console.Error.WriteLine("Usage: ContestSupport <input.docx> <output.docx> <screenshot-directory>");
    return 2;
}

var inputPath = Path.GetFullPath(args[0]);
var outputPath = Path.GetFullPath(args[1]);
var screenshotDirectory = Path.GetFullPath(args[2]);

if (!File.Exists(inputPath))
{
    throw new FileNotFoundException("Input DOCX was not found.", inputPath);
}

var screenshotNames = new[]
{
    "contest-01-pdf-upload-ocr.png",
    "contest-02-outline-cnn-section.png",
    "contest-03-model-settings-history.png",
    "contest-04-model-discovery-mock.png",
    "contest-05-model-test.png",
    "contest-06-generation-running.png",
    "contest-07-collaboration-completed.png",
};

foreach (var name in screenshotNames)
{
    var path = Path.Combine(screenshotDirectory, name);
    if (!File.Exists(path))
    {
        throw new FileNotFoundException("Required screenshot was not found.", path);
    }
}

Directory.CreateDirectory(Path.GetDirectoryName(outputPath)!);
File.Copy(inputPath, outputPath, overwrite: true);

using var document = WordprocessingDocument.Open(outputPath, isEditable: true);
var mainPart = document.MainDocumentPart ?? throw new InvalidOperationException("The document has no main document part.");
var body = mainPart.Document.Body ?? throw new InvalidOperationException("The document has no body.");
var paragraphs = body.Elements<Paragraph>().ToList();

var captionAnchor = paragraphs.FirstOrDefault(p => GetText(p) == "图5  督导智能体点评教学过程")
    ?? throw new InvalidOperationException("Could not find the existing Figure 5 caption.");
var target = captionAnchor.NextSibling<Paragraph>()
    ?? throw new InvalidOperationException("Could not find the page-break paragraph after Figure 5.");
var tocInnovationTwo = paragraphs.FirstOrDefault(p => GetText(p).StartsWith("创新点二：情境生成", StringComparison.Ordinal))
    ?? throw new InvalidOperationException("Could not find the innovation-two TOC entry.");
var tocPages = new Dictionary<string, int>(StringComparer.Ordinal)
{
    ["一、基础材料"] = 2,
    ["1. 申报书基本信息"] = 2,
    ["2. 课堂教学目标与思政育人目标"] = 2,
    ["3. 教学设计总体架构"] = 2,
    ["4. 教学全流程工具说明与教学理念"] = 3,
    ["二、创新性"] = 4,
    ["创新点一：智能备课"] = 4,
    ["创新点二：情境生成"] = 12,
    ["创新点三：交互教学"] = 13,
    ["创新点四：过程评价"] = 15,
    ["创新点五：迭代优化"] = 17,
    ["创新模式总图"] = 17,
    ["三、实施效果"] = 20,
    ["1. 课中互动：学习通测评、热云图、分组练习、AI实践"] = 20,
    ["2. 课后评价：学习通分析结果、评估结果、成绩分析"] = 22,
    ["四、应用潜力"] = 24,
    ["1. 渐进式实施路径（试点—迭代—推广）"] = 24,
    ["2. 标准化方案与可复制推广"] = 24,
};

foreach (var entry in tocPages)
{
    var paragraph = paragraphs.FirstOrDefault(p => GetText(p).StartsWith(entry.Key, StringComparison.Ordinal));
    if (paragraph is not null)
    {
        UpdateTocEntry(paragraph, entry.Key, entry.Value);
    }
}

var tocSupport = CreateTocEntry(tocInnovationTwo, "4. MAP平台实际操作支撑（PDF实测）", 6, "_toc_bm_map_support");
body.InsertBefore(tocSupport, tocInnovationTwo);
var headingSample = paragraphs.First(p => GetText(p) == "3. 使用过程");
var bodySample = paragraphs.First(p => GetText(p).StartsWith("正式备课阶段", StringComparison.Ordinal));
var imageSample = paragraphs.First(p => p.Descendants<Drawing>().Any());
var captionSample = captionAnchor;

var supportHeading = CreateHeadingParagraph(headingSample, "4. MAP平台实际操作支撑（PDF实测）");
AddBookmark(supportHeading, "1000", "_toc_bm_map_support");
var blocks = new List<OpenXmlElement>
{
    supportHeading,
    CreateTextParagraph(bodySample, "为验证上述方法不是停留在概念层面，教师使用《第10章深度学习与大语言模型（工业AI）》PDF作为本次实测材料，在MAP多智能体协同平台完成“导入—解析—选定—配置—生成—协作点评—迭代”的完整备课流程。该文件为39页扫描版PDF，平台对无文本页面自动启用中文OCR，最终识别39/39页，提取约6,697字，解析质量评分95，并将内容拆分为29个可预览分区、12个候选知识点。"),
    CreateTextParagraph(bodySample, "（1）材料导入与质量确认。教师从“材料预览”入口上传指定PDF，平台先给出文件类型、页数、文本量、OCR页数和解析质量提示，再展示目录与分区。教师可以在启动教学设计前确认材料是否被完整识别，避免直接对不可读或缺页材料生成方案。"),
    CreateImageParagraph(mainPart, imageSample, Path.Combine(screenshotDirectory, screenshotNames[0]), 23, "图23  指定PDF上传、OCR解析质量与材料分区预览"),
    CreateCaptionParagraph(captionSample, "图23  指定PDF上传、OCR解析质量与材料分区预览"),
    CreateTextParagraph(bodySample, "（2）目录与局部内容预览。平台将扫描页恢复为可阅读文本，并按章节、节标题和内容块生成目录。教师点击“10.2.1 卷积神经网络的结构”等分区即可查看原文，先核对课程范围和内容边界，再进入教学设计，减少整本材料被一次性泛化处理的风险。"),
    CreateImageParagraph(mainPart, imageSample, Path.Combine(screenshotDirectory, screenshotNames[1]), 24, "图24  目录分区与卷积神经网络知识内容预览"),
    CreateCaptionParagraph(captionSample, "图24  目录分区与卷积神经网络知识内容预览"),
    CreateTextParagraph(bodySample, "（3）知识点范围与教学参数。教师可以从候选知识点中多选本轮重点，配合课时滑块、讲解深度等参数明确“讲什么、讲到什么程度、用多长时间”。平台保留已确认的知识范围，后续迭代默认围绕同一组知识点重做方案，而不是把下一轮误当成全新课程。"),
    CreateTextParagraph(bodySample, "（4）模型选择、历史与连接检查。设置区支持按URL连接兼容模型，记录最近使用的模型和调用次数；在正式生成前可以发现模型列表、执行连接测试并看到延迟结果。本次正式配置为DeepSeek兼容接口与deepseek-v4-flash，连接测试返回正常；截图中的本地演示模型用于固定生成界面回归，便于材料复核，完成后已恢复正式模型配置。"),
    CreateImageParagraph(mainPart, imageSample, Path.Combine(screenshotDirectory, screenshotNames[2]), 25, "图25  模型选择、DeepSeek配置与历史记录"),
    CreateCaptionParagraph(captionSample, "图25  模型选择、DeepSeek配置与历史记录"),
    CreateImageParagraph(mainPart, imageSample, Path.Combine(screenshotDirectory, screenshotNames[3]), 26, "图26  按URL发现可用模型并选择模型"),
    CreateCaptionParagraph(captionSample, "图26  按URL发现可用模型并选择模型"),
    CreateImageParagraph(mainPart, imageSample, Path.Combine(screenshotDirectory, screenshotNames[4]), 27, "图27  生成前模型连接测试与延迟反馈"),
    CreateCaptionParagraph(captionSample, "图27  生成前模型连接测试与延迟反馈"),
    CreateTextParagraph(bodySample, "（5）生成过程可观测。启动教学设计后，顶部状态区持续显示当前阶段、已完成步骤、运行时长、后端心跳、Token数量、输出速度和预计耗时；中途出现网络等待时，教师可以区分“正在解析、正在生成、正在汇总”与异常停滞，并可暂停、继续或取消，避免长时间等待时失去判断依据。"),
    CreateImageParagraph(mainPart, imageSample, Path.Combine(screenshotDirectory, screenshotNames[5]), 28, "图28  教学设计生成中的阶段、Token与心跳状态"),
    CreateCaptionParagraph(captionSample, "图28  教学设计生成中的阶段、Token与心跳状态"),
    CreateTextParagraph(bodySample, "（6）三列协作与督导反馈。生成完成后，教师、学生、督导三列并列呈现同一轮教学设计的协作结果。教师列突出讲解逻辑和教学环节，学生列呈现不同认知层次的反馈，督导列将意见压缩为“优点、不足、建议”三组要点，便于教师快速定位问题并复制为下一轮优化提示词。平台支持在同一知识范围内重复打磨，形成“意见—再生成—再评价”的可追踪记录。"),
    CreateImageParagraph(mainPart, imageSample, Path.Combine(screenshotDirectory, screenshotNames[6]), 29, "图29  教师、学生、督导三列协作与分点督导意见"),
    CreateCaptionParagraph(captionSample, "图29  教师、学生、督导三列协作与分点督导意见"),
    CreateTextParagraph(bodySample, "本次实测形成的支撑证据覆盖材料可读性、知识范围可控性、模型可用性、生成过程可观测性和结果可评价性五个层面。教师可据此先预览和圈定内容，再启动多智能体备课，并将督导建议沉淀为下一轮提示词，避免“上传即生成”造成的范围失控；学生智能体反馈仅作为教师备课阶段的模拟依据，不替代真实课堂中的学生作答和学习评价。"),
};

foreach (var block in blocks)
{
    body.InsertBefore(block, target);
}

mainPart.Document.Save();
document.Dispose();

using var baseline = WordprocessingDocument.Open(inputPath, isEditable: false);
var baselineErrors = new OpenXmlValidator(FileFormatVersions.Office2019).Validate(baseline).ToList();

using (var check = WordprocessingDocument.Open(outputPath, isEditable: false))
{
    var errors = new OpenXmlValidator(FileFormatVersions.Office2019).Validate(check).ToList();
    var baselineDescriptions = baselineErrors
        .Select(error => error.Description)
        .OrderBy(description => description, StringComparer.Ordinal)
        .ToList();
    var outputDescriptions = errors
        .Select(error => error.Description)
        .OrderBy(description => description, StringComparer.Ordinal)
        .ToList();
    if (!baselineDescriptions.SequenceEqual(outputDescriptions, StringComparer.Ordinal))
    {
        foreach (var error in errors.Except(baselineErrors).Take(20))
        {
            Console.Error.WriteLine($"{error.Path?.XPath}: {error.Description}");
        }

        throw new InvalidDataException($"OpenXML validation introduced {Math.Max(0, errors.Count - baselineErrors.Count)} new error(s).");
    }

    if (errors.Count > 0)
    {
        Console.WriteLine($"OpenXML validation: passed with {errors.Count} pre-existing baseline issue(s).");
    }

    var checkedBody = check.MainDocumentPart?.Document.Body
        ?? throw new InvalidDataException("Document body is missing.");
    var checkedText = checkedBody.InnerText;
    var requiredText = new[]
    {
        "4. MAP平台实际操作支撑（PDF实测）",
        "图23  指定PDF上传、OCR解析质量与材料分区预览",
        "图24  目录分区与卷积神经网络知识内容预览",
        "图25  模型选择、DeepSeek配置与历史记录",
        "图26  按URL发现可用模型并选择模型",
        "图27  生成前模型连接测试与延迟反馈",
        "图28  教学设计生成中的阶段、Token与心跳状态",
        "图29  教师、学生、督导三列协作与分点督导意见",
    };
    var missingText = requiredText.Where(value => !checkedText.Contains(value, StringComparison.Ordinal)).ToList();
    if (missingText.Count > 0)
    {
        throw new InvalidDataException($"Missing inserted content: {string.Join("; ", missingText)}");
    }

    if (checkedBody.Descendants<Drawing>().Count() != 29)
    {
        throw new InvalidDataException("Expected 29 inline drawings after inserting the seven screenshots.");
    }
}

Console.WriteLine($"Created: {outputPath}");
Console.WriteLine($"Inserted blocks: {blocks.Count}");
return 0;

static string GetText(Paragraph paragraph)
    => string.Concat(paragraph.Descendants<Text>().Select(text => text.Text));

static Paragraph CreateTextParagraph(Paragraph sample, string text)
{
    var paragraph = new Paragraph();
    if (sample.ParagraphProperties is not null)
    {
        paragraph.Append((ParagraphProperties)sample.ParagraphProperties.CloneNode(true));
    }

    var run = new Run();
    var sampleRunProperties = sample.Elements<Run>().FirstOrDefault()?.RunProperties;
    if (sampleRunProperties is not null)
    {
        run.Append((RunProperties)sampleRunProperties.CloneNode(true));
    }

    run.Append(new Text(text) { Space = SpaceProcessingModeValues.Preserve });
    paragraph.Append(run);
    return paragraph;
}

static Paragraph CreateHeadingParagraph(Paragraph sample, string text)
{
    var paragraph = CreateTextParagraph(sample, text);
    var properties = paragraph.ParagraphProperties
        ?? throw new InvalidOperationException("The heading sample has no paragraph properties.");
    var style = properties.GetFirstChild<ParagraphStyleId>();
    if (style is not null && properties.GetFirstChild<KeepNext>() is null)
    {
        properties.InsertAfter(new KeepNext(), style);
    }

    return paragraph;
}

static void AddBookmark(Paragraph paragraph, string id, string name)
{
    var firstRun = paragraph.Elements<Run>().FirstOrDefault()
        ?? throw new InvalidOperationException("The bookmark paragraph has no run.");
    paragraph.InsertBefore(new BookmarkStart { Id = id, Name = name }, firstRun);
    paragraph.Append(new BookmarkEnd { Id = id });
}

static Paragraph CreateTocEntry(Paragraph sample, string title, int page, string bookmarkName)
{
    var paragraph = (Paragraph)sample.CloneNode(true);
    var hyperlink = paragraph.Elements<Hyperlink>().FirstOrDefault()
        ?? throw new InvalidOperationException("The TOC sample has no hyperlink.");
    hyperlink.Anchor = bookmarkName;
    UpdateTocEntry(paragraph, title, page);
    return paragraph;
}

static void UpdateTocEntry(Paragraph paragraph, string title, int page)
{
    var hyperlink = paragraph.Elements<Hyperlink>().FirstOrDefault()
        ?? throw new InvalidOperationException("The TOC entry has no hyperlink.");
    var runs = hyperlink.Elements<Run>().ToList();
    if (runs.Count < 2)
    {
        throw new InvalidOperationException("The TOC entry does not have title and page runs.");
    }

    var titleText = runs[0].GetFirstChild<Text>()
        ?? throw new InvalidOperationException("The TOC title run has no text.");
    var pageText = runs[1].GetFirstChild<Text>()
        ?? throw new InvalidOperationException("The TOC page run has no text.");
    titleText.Text = title;
    titleText.Space = SpaceProcessingModeValues.Preserve;
    pageText.Text = $"\t{page}";
    pageText.Space = SpaceProcessingModeValues.Preserve;
}

static Paragraph CreateCaptionParagraph(Paragraph sample, string text)
    => CreateTextParagraph(sample, text);

static Paragraph CreateImageParagraph(MainDocumentPart mainPart, Paragraph sample, string imagePath, uint docPropertyId, string description)
{
    var paragraph = new Paragraph();
    if (sample.ParagraphProperties is not null)
    {
        paragraph.Append((ParagraphProperties)sample.ParagraphProperties.CloneNode(true));
    }

    var imagePart = mainPart.AddImagePart(ImagePartType.Png);
    using (var stream = File.OpenRead(imagePath))
    {
        imagePart.FeedData(stream);
    }

    var relationshipId = mainPart.GetIdOfPart(imagePart);
    const double widthInches = 6.2;
    const double heightInches = 4.3056;
    var cx = (long)(widthInches * 914400);
    var cy = (long)(heightInches * 914400);
    var drawing = new Drawing(
        new DW.Inline(
            new DW.Extent { Cx = cx, Cy = cy },
            new DW.EffectExtent { LeftEdge = 0L, TopEdge = 0L, RightEdge = 0L, BottomEdge = 0L },
            new DW.DocProperties { Id = docPropertyId, Name = $"MAPScreenshot{docPropertyId}", Description = description },
            new DW.NonVisualGraphicFrameDrawingProperties(new A.GraphicFrameLocks { NoChangeAspect = true }),
            new A.Graphic(
                new A.GraphicData(
                    new PIC.Picture(
                        new PIC.NonVisualPictureProperties(
                            new PIC.NonVisualDrawingProperties { Id = docPropertyId, Name = Path.GetFileName(imagePath) },
                            new PIC.NonVisualPictureDrawingProperties()),
                        new PIC.BlipFill(
                            new A.Blip { Embed = relationshipId, CompressionState = A.BlipCompressionValues.Print },
                            new A.Stretch(new A.FillRectangle())),
                        new PIC.ShapeProperties(
                            new A.Transform2D(
                                new A.Offset { X = 0L, Y = 0L },
                                new A.Extents { Cx = cx, Cy = cy }),
                            new A.PresetGeometry(new A.AdjustValueList()) { Preset = A.ShapeTypeValues.Rectangle })))
                { Uri = "http://schemas.openxmlformats.org/drawingml/2006/picture" }))
        {
            DistanceFromTop = 0U,
            DistanceFromBottom = 0U,
            DistanceFromLeft = 0U,
            DistanceFromRight = 0U,
        });

    paragraph.Append(new Run(drawing));
    return paragraph;
}
