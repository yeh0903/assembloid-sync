// args: src|outdir|prefix|mode|saturated   (paths with forward slashes)
args = getArgument();
parts = split(args, "|");
src = parts[0]; outdir = parts[1]; prefix = parts[2];
mode = parts[3]; saturated = parts[4];
setBatchMode(true);
run("Bio-Formats Importer", "open=[" + src + "] autoscale color_mode=Default rois_import=[ROI manager] view=Hyperstack stack_order=XYCZT use_virtual_stack");
setSlice(1);
if (mode == "auto_bc") {
    // ij.plugin.frame.ContrastAdjuster.autoAdjust, first click (threshold = pixels/5000)
    getRawStatistics(nPixels, mean, dmin, dmax);
    getHistogram(values, counts, 256);
    limit = nPixels / 10;
    threshold = nPixels / 5000;
    i = -1; found = false;
    do { i++; c = counts[i]; if (c > limit) c = 0; found = c > threshold; } while (!found && i < 255);
    hmin = i;
    i = 256; found = false;
    do { i--; c = counts[i]; if (c > limit) c = 0; found = c > threshold; } while (!found && i > 0);
    hmax = i;
    binSize = (dmax - dmin) / 256;
    lo = dmin + hmin * binSize;
    hi = dmin + hmax * binSize;
} else {
    run("Enhance Contrast", "saturated=" + saturated);
    getMinAndMax(lo, hi);
}
print("display range: " + d2s(lo, 8) + " .. " + d2s(hi, 8));
n = nSlices;
for (i = 1; i <= n; i++) {
    setSlice(i);
    run("Duplicate...", "title=__frm");
    setMinAndMax(lo, hi);
    saveAs("Tiff", outdir + "/" + prefix + IJ.pad(i - 1, 4) + ".tif");
    close();
}
close();
File.saveString("ok", outdir + "/DONE_SENTINEL.txt");
print("DONE_OK n=" + n);
eval("script", "System.exit(0);");
