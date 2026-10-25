import AVFoundation
import Foundation
// Match OpenCV 4.10's AVFoundation order, including muxed camera devices.
let devices = (AVCaptureDevice.devices(for: .video) + AVCaptureDevice.devices(for: .muxed)).sorted { $0.uniqueID < $1.uniqueID }
let records = devices.map { ["name": $0.localizedName, "uid": $0.uniqueID] }
let data = try JSONSerialization.data(withJSONObject: records)
print(String(data: data, encoding: .utf8)!)
