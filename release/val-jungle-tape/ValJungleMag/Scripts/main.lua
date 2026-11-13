-- Val Jungle 40rd BlueTape - UE4SS Lua
-- Double magazine visual (2x WP_AS_Val_Mag_Medium + blue tape) at runtime
-- Patches BP_AS_Val_Mag_Med MaxStackSize 20->40 at runtime, no uasset crash
print("[ValJungleMag] Loading...")

-- Blue tape material (will try to find/create a simple blue translucent material)
local TAPE_MATERIAL_PATH = "/Game/ITR2/Art/Items/Weapons/Rifles/AS_Val/Mag/MI_BlueTape"
local MAG_MESH_PATH = "/Game/ITR2/Art/Items/Weapons/Rifles/AS_Val/Mag/WP_AS_Val_Mag_Medium"

-- Magazine dimensions (approximate from mesh bounds)
local MAG_LENGTH = 22.0  -- cm, length along Y
local MAG_WIDTH = 5.5    -- cm, width along X
local MAG_THICKNESS = 3.0 -- cm, thickness along Z
local TAPE_THICKNESS = 0.3 -- cm

-- Hook when mag is constructed
RegisterHook("/Game/ITR2/BPs/Items/Firearms/Primary/Val_and_VSS/BP_AS_Val_Mag_Med.BP_AS_Val_Mag_Med_C:UserConstructionScript", function(Context)
    -- Find BPC_ItemStackComponent on this mag
    local bpc = Context:getPropertyValue("BPC_ItemStackComponent")
    if bpc and bpc:IsValid() then
        local cur = bpc:getPropertyValue("MaxStackSize")
        if cur == 20 then
            bpc:setPropertyValue("MaxStackSize", 40)
            print("[ValJungleMag] Patched mag 20->40 on " .. Context:GetFullName())
        end
    end
    
    -- Add double magazine visual + tape
    AddDoubleMagVisual(Context)
end)

-- Also patch existing instances in world
RegisterHook("/Script/Engine.PlayerController:ClientRestart", function()
    print("[ValJungleMag] ClientRestart - scanning for mags")
    local mags = FindAllOf("BP_AS_Val_Mag_Med_C")
    if mags then
        for i, mag in ipairs(mags) do
            local bpc = mag:getPropertyValue("BPC_ItemStackComponent")
            if bpc and bpc:IsValid() then
                if bpc:getPropertyValue("MaxStackSize") == 20 then
                    bpc:setPropertyValue("MaxStackSize", 40)
                end
            end
            -- Add visual to existing mags too
            AddDoubleMagVisual(mag)
        end
        print("[ValJungleMag] Patched " .. #mags .. " mags")
    end
end)

function AddDoubleMagVisual(mag)
    if not mag or not mag:IsValid() then return end
    
    -- Check if already processed
    local already = mag:getPropertyValue("ValJungleMag_Processed")
    if already then return end
    mag:setPropertyValue("ValJungleMag_Processed", true)
    
    -- Get the root component to attach to
    local root = mag:GetRootComponent()
    if not root or not root:IsValid() then
        print("[ValJungleMag] No valid root component on " .. mag:GetFullName())
        return
    end
    
    -- Find existing SkeletalMeshComponent (the original magazine mesh)
    local existingMesh = nil
    local components = mag:K2_GetComponentsByClass(StaticFindObject("/Script/Engine.SkeletalMeshComponent"))
    if components and #components > 0 then
        existingMesh = components[1]
    end
    
    if not existingMesh or not existingMesh:IsValid() then
        print("[ValJungleMag] No existing SkeletalMeshComponent found")
        return
    end
    
    -- Hide the original mesh (we'll replace with our two meshes)
    existingMesh:SetVisibility(false)
    
    -- Create Mag 1 (original orientation, offset -half length)
    local mag1 = NewObject("/Script/Engine.SkeletalMeshComponent", mag, "Mag1_Jungle")
    if mag1 and mag1:IsValid() then
        mag1:SetSkeletalMesh(StaticFindObject(MAG_MESH_PATH))
        mag1:RegisterComponent()
        mag1:AttachToComponent(root, FName("None"), EAttachmentRule.SnapToTarget, EAttachmentRule.SnapToTarget, EAttachmentRule.KeepWorld, false)
        -- Position at -MAG_LENGTH/2 so center is at origin
        mag1:SetRelativeLocation(FVector(0, -MAG_LENGTH/2, 0))
        mag1:SetRelativeRotation(FRotator(0, 0, 0))
        mag1:SetVisibility(true)
        print("[ValJungleMag] Created Mag1 on " .. mag:GetFullName())
    end
    
    -- Create Mag 2 (flipped 180° on Roll, offset +half length)
    local mag2 = NewObject("/Script/Engine.SkeletalMeshComponent", mag, "Mag2_Jungle")
    if mag2 and mag2:IsValid() then
        mag2:SetSkeletalMesh(StaticFindObject(MAG_MESH_PATH))
        mag2:RegisterComponent()
        mag2:AttachToComponent(root, FName("None"), EAttachmentRule.SnapToTarget, EAttachmentRule.SnapToTarget, EAttachmentRule.KeepWorld, false)
        -- Position at +MAG_LENGTH/2, rotated 180° on Roll (Y axis in UE is forward, Roll is X)
        mag2:SetRelativeLocation(FVector(0, MAG_LENGTH/2, 0))
        mag2:SetRelativeRotation(FRotator(180, 0, 0))  -- Roll 180 = flip upside down
        mag2:SetVisibility(true)
        print("[ValJungleMag] Created Mag2 on " .. mag:GetFullName())
    end
    
    -- Create Tape (simple box in the middle)
    -- Try to use a basic cube mesh
    local tapeMesh = StaticFindObject("/Engine/BasicShapes/Cube.Cube")
    if not tapeMesh then
        tapeMesh = StaticFindObject("/Engine/BasicShapes/Cube")
    end
    
    if tapeMesh then
        local tape = NewObject("/Script/Engine.StaticMeshComponent", mag, "Tape_Jungle")
        if tape and tape:IsValid() then
            tape:SetStaticMesh(tapeMesh)
            tape:RegisterComponent()
            tape:AttachToComponent(root, FName("None"), EAttachmentRule.SnapToTarget, EAttachmentRule.SnapToTarget, EAttachmentRule.KeepWorld, false)
            -- Tape in the middle, scaled to wrap around both mags
            -- Scale: X=width+tape, Y=tape_thickness, Z=thickness+tape
            tape:SetRelativeLocation(FVector(0, 0, 0))
            tape:SetRelativeScale3D(FVector(
                (MAG_WIDTH + TAPE_THICKNESS * 2) / 100.0,  -- Cube is 100x100x100 by default
                TAPE_THICKNESS / 100.0,
                (MAG_THICKNESS + TAPE_THICKNESS * 2) / 100.0
            ))
            tape:SetVisibility(true)
            
            -- Try to set blue tape material
            local tapeMat = StaticFindObject(TAPE_MATERIAL_PATH)
            if tapeMat then
                tape:SetMaterial(0, tapeMat)
            else
                -- Create a simple blue material instance at runtime
                CreateBlueTapeMaterial(tape)
            end
            print("[ValJungleMag] Created Tape on " .. mag:GetFullName())
        end
    else
        print("[ValJungleMag] Warning: Could not find Cube mesh for tape")
    end
end

function CreateBlueTapeMaterial(tapeComp)
    -- Try to create a dynamic material instance with blue color
    local baseMat = StaticFindObject("/Engine/EngineMaterials/DefaultMaterial.DefaultMaterial")
    if baseMat then
        local dynMat = tapeComp:CreateDynamicMaterialInstance(0, baseMat)
        if dynMat then
            -- Set base color to blue (#004AAD - electrical tape blue)
            dynMat:SetVectorParameterValue(FName("BaseColor"), FLinearColor(0.0, 0.29, 0.68, 1.0))
            -- Increase roughness for tape look
            dynMat:SetScalarParameterValue(FName("Roughness"), 0.8)
            dynMat:SetScalarParameterValue(FName("Metallic"), 0.0)
            print("[ValJungleMag] Created dynamic blue tape material")
        end
    end
end

print("[ValJungleMag] Ready - double mag 2x20 + blue tape visual at runtime")